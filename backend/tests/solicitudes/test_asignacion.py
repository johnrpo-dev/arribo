"""Asignación (1a-08) contra PostgreSQL: disponibilidad de conductores, grúa guardada en el
servicio, orden de ronda, reasignar y la pantalla de detalle (asignar sin recargar)."""
import importlib
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from configuracion.models import MomentoPlacaVin, configuracion_vigente
from flota.models import AsignacionConductorGrua, Conductor, Grua
from nucleo.estados import Estado, Resolucion
from nucleo.ronda import MovimientoInvalido
from solicitudes import operaciones
from solicitudes.disponibilidad import disponibilidad_de_conductores, motivos_de_bloqueo
from solicitudes.models import EstadoRegistro, EventoEstado, Servicio
from solicitudes.operaciones import ConductorBloqueado, MismoConductor

from ..conftest import crear_solicitud

pytestmark = pytest.mark.django_db

E = Estado


def de(conductor):
    """La disponibilidad de un conductor en la lista."""
    return next(d for d in disponibilidad_de_conductores() if d.conductor == conductor)


def url_asignar(servicio):
    return f"/solicitudes/{servicio.solicitud_id}/servicios/{servicio.pk}/asignar/"


def url_mover(solicitud, servicio):
    return f"/solicitudes/{solicitud.pk}/servicios/{servicio.pk}/ronda/"


@pytest.fixture
def logistica(client, crear_usuario):
    usuario = crear_usuario("logistica")
    client.force_login(usuario)
    return usuario


# --- Disponibilidad ----------------------------------------------------------------------------


def test_conductor_con_grua_vigente_operativa_esta_disponible(ana, grua1):
    disponibilidad = de(ana)
    assert disponibilidad.grua == grua1
    assert not disponibilidad.bloqueado
    assert motivos_de_bloqueo(ana) == []


def test_conductor_sin_grua_vigente_esta_bloqueado_con_su_motivo():
    carla = Conductor.objects.create(nombre="Carla", celular="3000000003")
    disponibilidad = de(carla)
    assert disponibilidad.grua is None
    assert disponibilidad.motivos == ("No tiene una grúa asignada en este momento.",)


def test_una_asignacion_conductor_grua_vencida_no_cuenta_como_vigente(grua1):
    carla = Conductor.objects.create(nombre="Carla", celular="3000000003")
    ahora = timezone.now()
    AsignacionConductorGrua.objects.create(
        conductor=carla, grua=grua1, inicio=ahora - timedelta(days=2), fin=ahora - timedelta(days=1)
    )
    assert de(carla).bloqueado


def test_grua_fuera_de_servicio_bloquea_al_conductor(ana, grua1):
    Grua.objects.filter(pk=grua1.pk).update(estado_operativo=Grua.EstadoOperativo.FUERA_DE_SERVICIO)
    assert de(ana).motivos == ("La grúa GRU001 está fuera de servicio.",)


def test_grua_inactiva_bloquea_al_conductor(ana, grua1):
    Grua.objects.filter(pk=grua1.pk).update(activa=False)
    assert de(ana).motivos == ("La grúa GRU001 está inactiva.",)


def test_conductor_inactivo_esta_bloqueado(ana):
    Conductor.objects.filter(pk=ana.pk).update(activo=False)
    assert de(ana).motivos == ("El conductor está inactivo.",)


def test_la_lista_pone_primero_a_los_disponibles(ana, beto):
    Conductor.objects.filter(pk=ana.pk).update(activo=False)
    nombres = [d.conductor.nombre for d in disponibilidad_de_conductores()]
    assert nombres == ["Beto", "Ana"]


def test_carga_y_montados_de_cada_conductor(crear_servicio, ana, beto):
    crear_servicio(E.ASIGNADO)
    crear_servicio(E.RECOGIDO)
    crear_servicio(E.NOVEDAD, previo=E.RECOGIDO)
    crear_servicio(E.NOVEDAD, previo=E.EN_CAMINO)
    crear_servicio(E.ENTREGADO)
    crear_servicio(E.CANCELADO)
    crear_servicio(E.EN_CAMINO, conductor=beto)
    crear_servicio()  # pendiente: no es de nadie
    assert (de(ana).no_terminales, de(ana).montados) == (4, 2)
    assert (de(beto).no_terminales, de(beto).montados) == (1, 0)


@pytest.mark.parametrize(
    "bloquear",
    [
        lambda ana, grua: Conductor.objects.filter(pk=ana.pk).update(activo=False),
        lambda ana, grua: Grua.objects.filter(pk=grua.pk).update(activa=False),
        lambda ana, grua: Grua.objects.filter(pk=grua.pk).update(
            estado_operativo=Grua.EstadoOperativo.FUERA_DE_SERVICIO
        ),
    ],
    ids=["conductor_inactivo", "grua_inactiva", "grua_fuera_de_servicio"],
)
def test_un_conductor_bloqueado_no_recibe_asignaciones_ni_reasignaciones(
    crear_servicio, ana, beto, grua1, usuario, bloquear
):
    pendiente = crear_servicio()
    de_beto = crear_servicio(E.ASIGNADO, conductor=beto)
    bloquear(ana, grua1)
    with pytest.raises(ConductorBloqueado, match="Ana no puede recibir servicios"):
        operaciones.asignar(pendiente, ana, actor=usuario)
    with pytest.raises(ConductorBloqueado):
        operaciones.reasignar(de_beto, ana, actor=usuario)
    pendiente.refresh_from_db()
    de_beto.refresh_from_db()
    assert (pendiente.estado, de_beto.conductor) == (E.PENDIENTE_ASIGNAR, beto)
    assert not EventoEstado.objects.exists()


def test_un_bloqueo_no_interrumpe_el_servicio_en_curso(crear_servicio, ana, grua1, usuario):
    servicio = crear_servicio(E.ASIGNADO)
    Grua.objects.filter(pk=grua1.pk).update(activa=False)
    operaciones.cambiar_estado(servicio, E.EN_CAMINO, actor=usuario)
    assert servicio.estado == E.EN_CAMINO


# --- La grúa queda guardada en el servicio -----------------------------------------------------


def test_el_servicio_conserva_la_grua_aunque_el_conductor_cambie_de_grua_despues(
    crear_servicio, ana, grua1, usuario
):
    servicio = crear_servicio()
    operaciones.asignar(servicio, ana, actor=usuario)
    # Ana pasa a otra grúa: se cierra la asignación vigente y se abre una nueva.
    ahora = timezone.now()
    AsignacionConductorGrua.objects.filter(conductor=ana, fin__isnull=True).update(fin=ahora)
    grua3 = Grua.objects.create(placa="GRU003", capacidad=2)
    AsignacionConductorGrua.objects.create(conductor=ana, grua=grua3, inicio=ahora)

    servicio.refresh_from_db()
    assert (servicio.conductor, servicio.grua) == (ana, grua1)
    assert de(ana).grua == grua3
    # Lo que se asigne ahora sale con la grúa nueva.
    otro = crear_servicio()
    operaciones.asignar(otro, ana, actor=usuario)
    assert otro.grua == grua3


def test_repartir_una_solicitud_de_tres_vehiculos_entre_dos_conductores(
    solicitud, crear_servicio, ana, beto, grua1, grua2, usuario
):
    uno, dos, tres = (crear_servicio() for _ in range(3))
    operaciones.asignar(uno, ana, actor=usuario)
    operaciones.asignar(dos, beto, actor=usuario)
    operaciones.asignar(tres, beto, actor=usuario)
    asignados = {
        s.pk: (s.conductor_id, s.grua_id, s.orden_ronda) for s in solicitud.servicios.all()
    }
    assert asignados == {
        uno.pk: (ana.pk, grua1.pk, 1),
        dos.pk: (beto.pk, grua2.pk, 1),
        tres.pk: (beto.pk, grua2.pk, 2),
    }
    assert solicitud.estado == "abierta"


def test_a_un_conductor_se_le_asignan_mas_vehiculos_que_su_capacidad(crear_servicio, ana, usuario):
    servicios = [crear_servicio() for _ in range(3)]  # la grúa de Ana tiene un puesto
    for servicio in servicios:
        operaciones.asignar(servicio, ana, actor=usuario)
    assert [s.orden_ronda for s in servicios] == [1, 2, 3]
    assert de(ana).no_terminales == 3


# --- Orden de ronda ----------------------------------------------------------------------------


def test_al_asignar_el_servicio_entra_al_final_de_la_ronda_aunque_haya_huecos(
    crear_servicio, ana, usuario
):
    primero, segundo, tercero = (crear_servicio() for _ in range(3))
    for servicio in (primero, segundo):
        operaciones.asignar(servicio, ana, actor=usuario)
    operaciones.cambiar_estado(primero, E.CANCELADO, actor=usuario, motivo="Desistió")
    operaciones.asignar(tercero, ana, actor=usuario)
    assert tercero.orden_ronda == 3
    assert [s.pk for s in operaciones.ronda_de(ana)] == [segundo.pk, tercero.pk]


def test_mover_en_la_ronda_cambia_el_orden_y_numera_de_nuevo(crear_servicio, ana, usuario):
    servicios = [crear_servicio() for _ in range(3)]
    for servicio in servicios:
        operaciones.asignar(servicio, ana, actor=usuario)
    operaciones.cambiar_estado(servicios[0], E.CANCELADO, actor=usuario, motivo="Desistió")
    eventos = EventoEstado.objects.count()
    nueva = operaciones.mover_en_ronda(servicios[2], "subir")
    assert nueva == [servicios[2].pk, servicios[1].pk]
    ordenes = dict(Servicio.objects.values_list("pk", "orden_ronda"))
    assert (ordenes[servicios[2].pk], ordenes[servicios[1].pk]) == (1, 2)
    assert EventoEstado.objects.count() == eventos  # mover no es un cambio de estado


def test_el_primero_de_la_ronda_no_sube(crear_servicio, ana, usuario):
    servicio = crear_servicio()
    operaciones.asignar(servicio, ana, actor=usuario)
    with pytest.raises(MovimientoInvalido, match="primero"):
        operaciones.mover_en_ronda(servicio, "subir")


def test_un_servicio_sin_conductor_no_se_mueve_en_ronda(crear_servicio):
    with pytest.raises(MovimientoInvalido):
        operaciones.mover_en_ronda(crear_servicio(), "bajar")


def test_la_base_no_deja_dos_servicios_activos_del_conductor_en_el_mismo_puesto(
    crear_servicio, ana
):
    primero = crear_servicio(E.ASIGNADO)
    segundo = crear_servicio(E.EN_CAMINO)
    Servicio.objects.filter(pk=primero.pk).update(orden_ronda=1)
    with (
        pytest.raises(IntegrityError, match="servicio_orden_ronda_unico_por_conductor"),
        transaction.atomic(),
    ):
        Servicio.objects.filter(pk=segundo.pk).update(orden_ronda=1)


def test_un_servicio_terminado_no_ocupa_puesto_en_la_ronda(crear_servicio, ana):
    entregado = crear_servicio(E.ENTREGADO)
    activo = crear_servicio(E.ASIGNADO)
    Servicio.objects.filter(pk__in=[entregado.pk, activo.pk]).update(orden_ronda=1)
    assert Servicio.objects.filter(orden_ronda=1).count() == 2


def test_la_migracion_numera_las_rondas_ya_guardadas_sin_tocar_los_terminados(
    crear_servicio, ana, beto
):
    from django.apps import apps

    migracion = importlib.import_module(
        "solicitudes.migrations.0003_orden_ronda_unico_por_conductor"
    )
    con_orden = crear_servicio(E.EN_CAMINO)
    Servicio.objects.filter(pk=con_orden.pk).update(orden_ronda=7)
    sin_orden = crear_servicio(E.ASIGNADO)
    de_beto = crear_servicio(E.ASIGNADO, conductor=beto)
    entregado = crear_servicio(E.ENTREGADO)

    migracion.numerar_rondas(apps, None)

    ordenes = dict(Servicio.objects.values_list("pk", "orden_ronda"))
    assert ordenes[con_orden.pk] == 1  # el que ya tenía orden queda primero
    assert ordenes[sin_orden.pk] == 2
    assert ordenes[de_beto.pk] == 1
    assert ordenes[entregado.pk] is None


def test_al_volver_a_la_cola_el_servicio_deja_la_ronda(crear_servicio, ana, usuario):
    servicio = crear_servicio()
    operaciones.asignar(servicio, ana, actor=usuario)
    operaciones.cambiar_estado(servicio, E.NOVEDAD, actor=usuario, motivo="Llanta")
    operaciones.resolver_novedad(servicio, Resolucion.REASIGNAR, actor=usuario)
    assert (servicio.conductor_id, servicio.orden_ronda) == (None, None)


# --- Reasignar ---------------------------------------------------------------------------------


def test_reasignar_pasa_el_servicio_al_final_de_la_ronda_del_otro_conductor(
    crear_servicio, ana, beto, grua2, usuario
):
    de_beto = crear_servicio()
    operaciones.asignar(de_beto, beto, actor=usuario)
    servicio = crear_servicio()
    operaciones.asignar(servicio, ana, actor=usuario)
    operaciones.reasignar(servicio, beto, actor=usuario, motivo="Ana quedó varada")
    assert (servicio.conductor, servicio.grua, servicio.orden_ronda) == (beto, grua2, 2)
    assert operaciones.ronda_de(ana) == []


def test_no_se_reasigna_al_mismo_conductor(crear_servicio, ana, usuario):
    servicio = crear_servicio(E.EN_CAMINO)
    with pytest.raises(MismoConductor):
        operaciones.reasignar(servicio, ana, actor=usuario)
    servicio.refresh_from_db()
    assert servicio.estado == E.EN_CAMINO
    assert not EventoEstado.objects.exists()


# --- Pantalla ----------------------------------------------------------------------------------


def test_el_detalle_de_una_abierta_ofrece_asignar_con_la_disponibilidad(
    client, logistica, crear_servicio, ana, beto
):
    servicio = crear_servicio()
    Conductor.objects.create(nombre="Carla", celular="3000000003")
    html = client.get(f"/solicitudes/{servicio.solicitud_id}/").content.decode()
    assert "Asignar conductores" in html
    assert url_asignar(servicio) in html
    assert "Ana · GRU001, 1 puesto · 0 en ronda, 0 montados" in html
    assert "Beto · GRU002, 2 puestos" in html
    assert "disabled>Carla · bloqueado: No tiene una grúa asignada" in html


def test_asignar_desde_el_detalle_y_volver_con_el_mensaje(
    client, logistica, crear_servicio, ana, grua1
):
    servicio = crear_servicio()
    respuesta = client.post(
        url_asignar(servicio), {f"s{servicio.pk}-conductor": ana.pk}, follow=True
    )
    servicio.refresh_from_db()
    assert (servicio.estado, servicio.conductor, servicio.grua) == (E.ASIGNADO, ana, grua1)
    assert EventoEstado.objects.get().actor == logistica
    html = respuesta.content.decode()
    assert f"Servicio N.º {servicio.pk} asignado a Ana." in html
    assert "Ronda de Ana" in html


def test_asignar_con_htmx_devuelve_el_detalle_actualizado(client, logistica, crear_servicio, ana):
    servicio = crear_servicio()
    respuesta = client.post(
        url_asignar(servicio),
        {f"s{servicio.pk}-conductor": ana.pk},
        headers={"HX-Request": "true"},
        follow=True,
    )
    assert respuesta.status_code == 200
    assert 'id="contenido"' in respuesta.content.decode()


def test_repartir_tres_vehiculos_entre_dos_conductores_desde_la_pantalla(
    client, logistica, solicitud, crear_servicio, ana, beto
):
    servicios = [crear_servicio() for _ in range(3)]
    for servicio, conductor in zip(servicios, (ana, beto, beto), strict=True):
        client.post(url_asignar(servicio), {f"s{servicio.pk}-conductor": conductor.pk})
    conductores = list(solicitud.servicios.order_by("pk").values_list("conductor__nombre", flat=True))
    assert conductores == ["Ana", "Beto", "Beto"]
    html = client.get(f"/solicitudes/{solicitud.pk}/").content.decode()
    assert "Ronda de Ana" in html and "Ronda de Beto" in html
    # La tabla de la solicitud sigue por número aunque la ronda de Beto cambie de orden.
    client.post(url_mover(solicitud, servicios[2]), {"direccion": "subir"})
    html = client.get(f"/solicitudes/{solicitud.pk}/").content.decode()
    posiciones = [html.index(f"N.º {s.pk} · ") for s in servicios]
    assert posiciones == sorted(posiciones)


def test_un_borrador_no_se_asigna_desde_la_vista(client, logistica, cliente, crear_servicio, ana):
    borrador = crear_solicitud(cliente, estado_registro=EstadoRegistro.BORRADOR)
    servicio = crear_servicio(solicitud_de=borrador)
    html = client.get(f"/solicitudes/{borrador.pk}/").content.decode()
    assert "Asignar conductores" not in html
    respuesta = client.post(
        url_asignar(servicio), {f"s{servicio.pk}-conductor": ana.pk}, follow=True
    )
    servicio.refresh_from_db()
    assert servicio.estado == E.PENDIENTE_ASIGNAR
    assert "La solicitud es un borrador" in respuesta.content.decode()


def test_el_error_de_placa_al_asignar_se_ve_en_la_pantalla(
    client, logistica, crear_servicio, nuevo_vehiculo, ana
):
    configuracion = configuracion_vigente()
    configuracion.momento_placa_vin = MomentoPlacaVin.AL_ASIGNAR
    configuracion.save()
    servicio = crear_servicio(vehiculo=nuevo_vehiculo(placa="", marca="Mazda"))
    respuesta = client.post(
        url_asignar(servicio), {f"s{servicio.pk}-conductor": ana.pk}, follow=True
    )
    html = respuesta.content.decode()
    assert "El vehículo necesita placa o VIN" in html
    assert "La configuración exige placa o VIN al asignar." in html
    servicio.refresh_from_db()
    assert servicio.estado == E.PENDIENTE_ASIGNAR


def test_un_conductor_bloqueado_enviado_a_la_fuerza_se_rechaza_con_el_motivo(
    client, logistica, crear_servicio
):
    carla = Conductor.objects.create(nombre="Carla", celular="3000000003")
    servicio = crear_servicio()
    respuesta = client.post(
        url_asignar(servicio), {f"s{servicio.pk}-conductor": carla.pk}, follow=True
    )
    assert "Carla no tiene una grúa asignada" in respuesta.content.decode()
    servicio.refresh_from_db()
    assert servicio.estado == E.PENDIENTE_ASIGNAR


def test_sin_elegir_conductor_no_se_asigna(client, logistica, crear_servicio):
    servicio = crear_servicio()
    respuesta = client.post(url_asignar(servicio), {}, follow=True)
    assert "Elija el conductor." in respuesta.content.decode()


def test_reasignar_desde_la_pantalla_con_motivo(client, logistica, crear_servicio, ana, beto):
    servicio = crear_servicio(E.EN_CAMINO)
    html = client.get(f"/solicitudes/{servicio.solicitud_id}/").content.decode()
    assert "Reasignar" in html
    client.post(
        url_asignar(servicio),
        {f"s{servicio.pk}-conductor": beto.pk, f"s{servicio.pk}-motivo": "Ana quedó varada"},
    )
    servicio.refresh_from_db()
    assert (servicio.estado, servicio.conductor) == (E.ASIGNADO, beto)
    assert EventoEstado.objects.get().motivo == "Ana quedó varada"


def test_un_servicio_ya_asignado_por_otra_persona_se_informa_sin_cambiarlo(
    client, logistica, crear_servicio, ana, beto, usuario
):
    servicio = crear_servicio()
    # La pantalla se cargó con el servicio pendiente; mientras tanto, otra persona lo asignó a
    # Beto y el conductor ya lo recogió. El formulario de "asignar" que llega no debe cambiarlo.
    operaciones.asignar(servicio, beto, actor=usuario)
    operaciones.cambiar_estado(servicio, E.EN_CAMINO, actor=usuario)
    operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    respuesta = client.post(
        url_asignar(servicio), {f"s{servicio.pk}-conductor": ana.pk}, follow=True
    )
    assert "su estado cambió mientras tanto" in respuesta.content.decode()
    servicio.refresh_from_db()
    assert servicio.conductor == beto


def test_mover_desde_la_pantalla(client, logistica, solicitud, crear_servicio, ana, usuario):
    primero, segundo = crear_servicio(), crear_servicio()
    for servicio in (primero, segundo):
        operaciones.asignar(servicio, ana, actor=usuario)
    respuesta = client.post(url_mover(solicitud, segundo), {"direccion": "subir"}, follow=True)
    assert "Ronda de Ana actualizada." in respuesta.content.decode()
    assert [s.pk for s in operaciones.ronda_de(ana)] == [segundo.pk, primero.pk]


def test_la_ronda_muestra_servicios_de_otras_solicitudes_con_enlace(
    client, logistica, cliente, solicitud, crear_servicio, ana, usuario
):
    otra = crear_solicitud(cliente, origen="Otra")
    aqui = crear_servicio()
    alla = crear_servicio(solicitud_de=otra)
    operaciones.asignar(alla, ana, actor=usuario)
    operaciones.asignar(aqui, ana, actor=usuario)
    html = client.get(f"/solicitudes/{solicitud.pk}/").content.decode()
    assert f'href="/solicitudes/{otra.pk}/"' in html


# --- Permisos ----------------------------------------------------------------------------------


@pytest.mark.parametrize("ruta", ["asignar", "ronda"])
def test_facturacion_no_asigna_ni_mueve(client, crear_usuario, crear_servicio, ana, ruta):
    client.force_login(crear_usuario("facturacion"))
    servicio = crear_servicio()
    url = f"/solicitudes/{servicio.solicitud_id}/servicios/{servicio.pk}/{ruta}/"
    assert client.post(url, {f"s{servicio.pk}-conductor": ana.pk}).status_code == 403
    servicio.refresh_from_db()
    assert servicio.estado == E.PENDIENTE_ASIGNAR


@pytest.mark.parametrize("ruta", ["asignar", "ronda"])
def test_sin_sesion_lleva_al_ingreso(client, crear_servicio, ruta):
    servicio = crear_servicio()
    url = f"/solicitudes/{servicio.solicitud_id}/servicios/{servicio.pk}/{ruta}/"
    respuesta = client.post(url)
    assert respuesta.status_code == 302
    assert respuesta.url.startswith("/ingresar/")


def test_asignar_solo_por_post(client, logistica, crear_servicio):
    servicio = crear_servicio()
    assert client.get(url_asignar(servicio)).status_code == 405


def test_un_servicio_de_otra_solicitud_no_se_asigna_por_esta_ruta(
    client, logistica, cliente, crear_servicio, ana
):
    otra = crear_solicitud(cliente)
    servicio = crear_servicio()
    url = f"/solicitudes/{otra.pk}/servicios/{servicio.pk}/asignar/"
    assert client.post(url, {f"s{servicio.pk}-conductor": ana.pk}).status_code == 404
