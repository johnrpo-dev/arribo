"""Registro de solicitud II, contra PostgreSQL: completar un borrador, varios vehículos, referencia
externa de aseguradora, nota del momento de placa o VIN, advertencia de duplicado, regreso de
eventos y cierre como no concretada.
"""
import pytest

from clientes.models import Cliente, TelefonoCliente, TipoCliente
from configuracion.models import MomentoPlacaVin, configuracion_vigente
from nucleo.estados import Estado
from nucleo.registro import CierreNoPermitido, Faltante
from solicitudes import operaciones, registro
from solicitudes.models import EstadoRegistro, EventoEstado, Servicio, Solicitud
from solicitudes.operaciones import SolicitudNoAsignable
from tests.conftest import VIN, crear_solicitud

from .test_registro import datos, formulario

pytestmark = pytest.mark.django_db

E = Estado
RUTA = "/solicitudes/nueva/"


def ruta(solicitud, accion=""):
    return f"/solicitudes/{solicitud.pk}/{accion}"


@pytest.fixture
def con_telefono(cliente):
    TelefonoCliente.objects.create(cliente=cliente, numero="3001234567")
    return cliente


@pytest.fixture
def logistica(client, crear_usuario):
    usuario = crear_usuario("logistica")
    client.force_login(usuario)
    return usuario


@pytest.fixture
def aseguradora():
    cliente = Cliente.objects.create(nombre="Seguros Andinos", tipo=TipoCliente.ASEGURADORA)
    TelefonoCliente.objects.create(cliente=cliente, numero="6045551234")
    return cliente


def vehiculo(placa="", **otros):
    return {"placa": placa, **otros}


def con_vehiculos(*filas, **cambios):
    """Los datos de `datos()` con varias filas de vehículos."""
    campos = datos(**cambios)
    for clave in list(campos):
        if clave.startswith("vehiculos-"):
            del campos[clave]
    return formulario(campos, list(filas))


def borrador_guardado(client, **cambios):
    client.post(RUTA, datos(accion="borrador", **cambios))
    return Solicitud.objects.latest("pk")


# --- Completar un borrador ---------------------------------------------------------------------


def test_el_detalle_de_un_borrador_enlaza_a_completarlo(client, logistica, con_telefono):
    solicitud = borrador_guardado(client)
    html = client.get(ruta(solicitud)).content.decode()
    assert f'href="/solicitudes/{solicitud.pk}/completar/"' in html


def test_el_detalle_de_una_abierta_no_ofrece_completarla(client, logistica, con_telefono):
    client.post(RUTA, datos())
    solicitud = Solicitud.objects.get()
    assert "completar/" not in client.get(ruta(solicitud)).content.decode()


def test_completar_muestra_el_formulario_con_los_datos_del_borrador(client, logistica, con_telefono):
    solicitud = borrador_guardado(client, destino="")
    html = client.get(ruta(solicitud, "completar/")).content.decode()
    assert f"Completar borrador {solicitud.pk}" in html
    assert 'value="3001234567"' in html
    assert 'value="Calle 10 # 43-20, El Poblado"' in html
    assert 'value="ABC123"' in html
    servicio = solicitud.servicios.get()
    assert f'name="vehiculos-0-servicio" value="{servicio.pk}"' in html
    assert "Quitar este vehículo" in html


def test_completar_los_obligatorios_abre_el_borrador(client, logistica, con_telefono):
    solicitud = borrador_guardado(client, destino="")
    servicio = solicitud.servicios.get()
    respuesta = client.post(
        ruta(solicitud, "completar/"),
        datos(destino="Carrera 70 # 1-50", servicio=str(servicio.pk)),
        follow=True,
    )
    assert respuesta.redirect_chain == [(f"/solicitudes/{solicitud.pk}/", 302)]
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA
    assert solicitud.destino == "Carrera 70 # 1-50"
    assert list(solicitud.servicios.all()) == [servicio]  # no se duplicó el servicio
    assert "Queda abierta" in respuesta.content.decode()


def test_completar_sin_los_obligatorios_sigue_en_borrador(client, logistica, con_telefono):
    solicitud = borrador_guardado(client, destino="")
    servicio = solicitud.servicios.get()
    respuesta = client.post(
        ruta(solicitud, "completar/"), datos(destino="", servicio=str(servicio.pk)), follow=True
    )
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.BORRADOR
    assert "Para abrirla falta el destino" in respuesta.content.decode()


def test_una_solicitud_abierta_no_se_edita_con_el_formulario(client, logistica, con_telefono):
    client.post(RUTA, datos())
    solicitud = Solicitud.objects.get()
    respuesta = client.get(ruta(solicitud, "completar/"), follow=True)
    assert respuesta.redirect_chain == [(f"/solicitudes/{solicitud.pk}/", 302)]
    assert "ya no es un borrador" in respuesta.content.decode()
    client.post(ruta(solicitud, "completar/"), datos(origen="Otro origen"))
    solicitud.refresh_from_db()
    assert solicitud.origen == "Calle 10 # 43-20, El Poblado"


def test_completar_borrador_rechaza_una_solicitud_que_ya_no_es_borrador(cliente, usuario):
    solicitud = crear_solicitud(cliente)
    with pytest.raises(registro.SolicitudNoEditable):
        registro.completar_borrador(
            solicitud, registro.DatosRegistro(tipo="traslado", solicitante=cliente), usuario=usuario
        )


def test_corregir_la_placa_de_un_vehiculo_del_borrador_cambia_el_vehiculo_del_servicio(
    client, logistica, con_telefono
):
    solicitud = borrador_guardado(client)
    servicio = solicitud.servicios.get()
    client.post(ruta(solicitud, "completar/"), datos(placa="xyz-789", servicio=str(servicio.pk)))
    servicio.refresh_from_db()
    assert servicio.vehiculo.placa == "XYZ789"
    assert solicitud.servicios.count() == 1


def test_un_vehiculo_sin_placa_ni_vin_se_corrige_sin_crear_otro(client, logistica, con_telefono):
    solicitud = borrador_guardado(client, placa="", marca="Mazda")
    servicio = solicitud.servicios.get()
    client.post(
        ruta(solicitud, "completar/"),
        datos(placa="", marca="Renault", linea="Logan", servicio=str(servicio.pk)),
    )
    servicio.refresh_from_db()
    assert (servicio.vehiculo.marca, servicio.vehiculo.linea) == ("Renault", "Logan")
    assert servicio.vehiculo_id == Servicio.objects.get().vehiculo_id


def test_quitar_un_vehiculo_del_borrador_cancela_su_servicio_con_motivo(
    client, logistica, con_telefono
):
    solicitud = borrador_guardado(client)
    quitado = solicitud.servicios.get()
    client.post(
        ruta(solicitud, "completar/"),
        con_vehiculos(
            vehiculo("ABC123", servicio=str(quitado.pk), quitar="on"),
            vehiculo("XYZ789"),
        ),
    )
    quitado.refresh_from_db()
    assert quitado.estado == E.CANCELADO
    evento = EventoEstado.objects.get(servicio=quitado)
    assert evento.motivo == registro.MOTIVO_QUITADO
    assert evento.actor == logistica
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA
    assert [s.vehiculo.placa for s in registro.servicios_de_ida(solicitud)] == ["XYZ789"]


def test_quitar_el_unico_vehiculo_deja_el_borrador_sin_vehiculos(client, logistica, con_telefono):
    solicitud = borrador_guardado(client)
    servicio = solicitud.servicios.get()
    client.post(ruta(solicitud, "completar/"), datos(servicio=str(servicio.pk), quitar="on"))
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.BORRADOR
    assert registro.faltantes_de(solicitud) == [Faltante.VEHICULO]


def test_un_servicio_de_otra_solicitud_no_se_edita_desde_este_borrador(
    client, logistica, con_telefono
):
    otra = borrador_guardado(client, placa="XYZ789")
    ajeno = otra.servicios.get()
    solicitud = borrador_guardado(client)
    respuesta = client.post(
        ruta(solicitud, "completar/"), datos(placa="ABC123", servicio=str(ajeno.pk), quitar="on")
    )
    assert "no es de esta solicitud" in respuesta.content.decode()
    ajeno.refresh_from_db()
    assert ajeno.estado == E.PENDIENTE_ASIGNAR


def test_una_fila_del_borrador_vacia_y_sin_quitar_se_rechaza(client, logistica, con_telefono):
    solicitud = borrador_guardado(client)
    servicio = solicitud.servicios.get()
    respuesta = client.post(
        ruta(solicitud, "completar/"),
        datos(placa="", marca="", linea="", color="", servicio=str(servicio.pk)),
    )
    assert "Escriba los datos del vehículo o marque Quitar." in respuesta.content.decode()


def test_facturacion_no_completa_borradores(client, crear_usuario, cliente):
    solicitud = crear_solicitud(cliente, estado_registro=EstadoRegistro.BORRADOR)
    client.force_login(crear_usuario("facturacion"))
    assert client.get(ruta(solicitud, "completar/")).status_code == 403
    assert client.post(ruta(solicitud, "no-concretada/"), {"motivo": "precio"}).status_code == 403


# --- Varios vehículos --------------------------------------------------------------------------


def test_cada_vehiculo_es_un_servicio(client, logistica, con_telefono):
    client.post(
        RUTA,
        con_vehiculos(vehiculo("ABC123"), vehiculo("", vin=VIN), vehiculo("DEF456", marca="Kia")),
    )
    solicitud = Solicitud.objects.get()
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA
    servicios = list(solicitud.servicios.order_by("pk"))
    assert [(s.vehiculo.placa, s.vehiculo.vin) for s in servicios] == [
        ("ABC123", ""),
        ("", VIN),
        ("DEF456", ""),
    ]
    assert all(s.estado == E.PENDIENTE_ASIGNAR for s in servicios)


def test_las_filas_vacias_no_crean_servicios(client, logistica, con_telefono):
    client.post(RUTA, con_vehiculos(vehiculo("ABC123"), vehiculo(""), vehiculo("")))
    assert Servicio.objects.count() == 1


def test_el_mismo_vehiculo_en_dos_filas_se_rechaza(client, logistica, con_telefono):
    respuesta = client.post(RUTA, con_vehiculos(vehiculo("ABC123"), vehiculo("abc 123")))
    assert "Este vehículo ya está en otra fila." in respuesta.content.decode()
    assert Solicitud.objects.count() == 0


def test_un_error_en_una_fila_queda_junto_a_su_campo(client, logistica, con_telefono):
    respuesta = client.post(
        RUTA, con_vehiculos(vehiculo("ABC123"), vehiculo("", vin="1HGCM82633A0O4352"))
    )
    html = respuesta.content.decode()
    assert "sin I, O ni Q" in html
    assert html.index('name="vehiculos-1-vin"') < html.index("sin I, O ni Q")
    assert Solicitud.objects.count() == 0


def test_referencia_sin_datos_del_vehiculo_se_rechaza(client, logistica, con_telefono):
    respuesta = client.post(
        RUTA, con_vehiculos(vehiculo("ABC123"), vehiculo("", referencia_externa="CASO-1"))
    )
    assert "Escriba la placa, el VIN u otro dato del vehículo." in respuesta.content.decode()


def test_agregar_vehiculo_devuelve_la_fila_siguiente_y_actualiza_el_total(client, logistica):
    html = client.get("/solicitudes/nueva/vehiculo/", {"indice": "2"}).content.decode()
    assert "Vehículo 3" in html
    assert 'name="vehiculos-2-placa"' in html
    assert 'name="vehiculos-TOTAL_FORMS" value="3"' in html
    assert 'hx-swap-oob="true"' in html
    assert '{"indice": 3}' in html  # el botón pide la fila siguiente
    assert "Quitar este vehículo" not in html


def test_el_formulario_nuevo_trae_una_fila_y_el_boton_de_agregar(client, logistica):
    html = client.get(RUTA).content.decode()
    assert 'name="vehiculos-0-placa"' in html
    assert 'name="vehiculos-1-placa"' not in html
    assert "Agregar otro vehículo" in html


# --- Referencia externa de aseguradora ---------------------------------------------------------


def test_si_paga_una_aseguradora_sin_referencia_queda_en_borrador(
    client, logistica, con_telefono, aseguradora
):
    respuesta = client.post(RUTA, datos(pagador_telefono="604 555 1234"), follow=True)
    solicitud = Solicitud.objects.get()
    assert solicitud.estado_registro == EstadoRegistro.BORRADOR
    assert "la referencia externa de la aseguradora en cada vehículo" in respuesta.content.decode()


def test_si_paga_una_aseguradora_con_referencia_en_cada_vehiculo_queda_abierta(
    client, logistica, con_telefono, aseguradora
):
    client.post(
        RUTA,
        con_vehiculos(
            vehiculo("ABC123", referencia_externa=" SIN-2026-001 "),
            vehiculo("XYZ789", referencia_externa="SIN-2026-002"),
            pagador_telefono="604 555 1234",
        ),
    )
    solicitud = Solicitud.objects.get()
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA
    assert sorted(solicitud.servicios.values_list("referencia_externa", flat=True)) == [
        "SIN-2026-001",
        "SIN-2026-002",
    ]


def test_si_a_un_vehiculo_le_falta_la_referencia_queda_en_borrador(
    client, logistica, con_telefono, aseguradora
):
    client.post(
        RUTA,
        con_vehiculos(
            vehiculo("ABC123", referencia_externa="SIN-1"),
            vehiculo("XYZ789"),
            pagador_telefono="604 555 1234",
        ),
    )
    assert Solicitud.objects.get().estado_registro == EstadoRegistro.BORRADOR


def test_si_la_aseguradora_es_quien_llama_tambien_exige_referencia(client, logistica, aseguradora):
    client.post(RUTA, datos(telefono="604 555 1234"))
    assert Solicitud.objects.get().estado_registro == EstadoRegistro.BORRADOR


def test_si_no_paga_una_aseguradora_la_referencia_es_opcional(client, logistica, con_telefono):
    client.post(RUTA, datos())
    assert Solicitud.objects.get().estado_registro == EstadoRegistro.ABIERTA


def test_completar_la_referencia_abre_el_borrador_de_aseguradora(
    client, logistica, con_telefono, aseguradora
):
    client.post(RUTA, datos(pagador_telefono="604 555 1234"))
    solicitud = Solicitud.objects.get()
    servicio = solicitud.servicios.get()
    html = client.get(ruta(solicitud, "completar/")).content.decode()
    assert 'value="6045551234"' in html  # el pagador se conserva al completar
    client.post(
        ruta(solicitud, "completar/"),
        datos(pagador_telefono="6045551234", servicio=str(servicio.pk), referencia_externa="C-9"),
    )
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA
    assert solicitud.pagador == aseguradora


# --- Momento de placa o VIN (nota del formulario) ----------------------------------------------


@pytest.mark.parametrize(
    "momento, texto",
    [(MomentoPlacaVin.AL_RECOGER, "al recoger"), (MomentoPlacaVin.AL_ASIGNAR, "al asignar")],
)
def test_el_formulario_dice_cuando_se_exigira_la_placa_o_el_vin(client, logistica, momento, texto):
    configuracion = configuracion_vigente()
    configuracion.momento_placa_vin = momento
    configuracion.save()
    html = client.get(RUTA).content.decode()
    assert f"La placa o el VIN se exigirán {texto}" in html


def test_al_asignar_configurado_el_panel_registra_sin_placa_pero_no_asigna(
    client, logistica, con_telefono, ana
):
    configuracion = configuracion_vigente()
    configuracion.momento_placa_vin = MomentoPlacaVin.AL_ASIGNAR
    configuracion.save()
    client.post(RUTA, datos(placa=""))
    servicio = Servicio.objects.get()
    assert servicio.solicitud.estado_registro == EstadoRegistro.ABIERTA
    with pytest.raises(operaciones.IdentificacionIncompleta):
        operaciones.asignar(servicio, ana, actor=logistica)


# --- Advertencia de duplicado ------------------------------------------------------------------


@pytest.fixture
def activo(cliente, crear_servicio, nuevo_vehiculo):
    """Un servicio pendiente de ABC123 en otra solicitud abierta."""
    return crear_servicio(vehiculo=nuevo_vehiculo(placa="ABC123", vin=VIN))


def test_un_vehiculo_con_servicio_activo_advierte_y_no_guarda(client, logistica, con_telefono, activo):
    respuesta = client.post(RUTA, datos())
    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "Posible duplicado" in html
    assert "ABC123 ya tiene un servicio activo en la" in html
    assert f'href="/solicitudes/{activo.solicitud_id}/"' in html
    assert "(Pendiente de asignar)" in html
    assert Solicitud.objects.count() == 1  # solo la del servicio activo


def test_al_confirmar_el_duplicado_se_guarda(client, logistica, con_telefono, activo):
    client.post(RUTA, datos())
    firma = f"ABC123@{activo.solicitud_id}"
    respuesta = client.post(RUTA, datos(duplicados_confirmados=firma), follow=True)
    assert Solicitud.objects.count() == 2
    nueva = Solicitud.objects.latest("pk")
    assert nueva.estado_registro == EstadoRegistro.ABIERTA
    assert nueva.servicios.get().vehiculo == activo.vehiculo
    assert respuesta.redirect_chain == [(f"/solicitudes/{nueva.pk}/", 302)]


def test_el_duplicado_tambien_se_detecta_por_vin(client, logistica, con_telefono, activo):
    html = client.post(RUTA, datos(placa="", vin=VIN)).content.decode()
    assert f"{VIN} ya tiene un servicio activo" in html


def test_otra_confirmacion_no_sirve_si_cambian_los_duplicados(
    client, logistica, con_telefono, activo, crear_servicio, nuevo_vehiculo
):
    crear_servicio(vehiculo=nuevo_vehiculo(placa="XYZ789"))
    firma = f"ABC123@{activo.solicitud_id}"
    respuesta = client.post(
        RUTA,
        con_vehiculos(vehiculo("ABC123"), vehiculo("XYZ789"), duplicados_confirmados=firma),
    )
    assert "XYZ789 ya tiene un servicio activo" in respuesta.content.decode()
    assert Solicitud.objects.count() == 1


@pytest.mark.parametrize("estado", [E.ENTREGADO, E.CANCELADO])
def test_un_servicio_terminado_no_es_duplicado(
    client, logistica, con_telefono, crear_servicio, nuevo_vehiculo, estado
):
    crear_servicio(estado, vehiculo=nuevo_vehiculo(placa="ABC123"))
    client.post(RUTA, datos())
    assert Solicitud.objects.count() == 2


@pytest.mark.parametrize("estado", [E.ASIGNADO, E.EN_CAMINO, E.RECOGIDO, E.NOVEDAD])
def test_un_servicio_en_curso_es_duplicado(
    con_telefono, crear_servicio, nuevo_vehiculo, estado
):
    servicio = crear_servicio(estado, vehiculo=nuevo_vehiculo(placa="ABC123"))
    duplicados = registro.duplicados_activos([registro.DatosVehiculo("ABC123", "")])
    assert [(d.identificacion, d.solicitud_id) for d in duplicados] == [
        ("ABC123", servicio.solicitud_id)
    ]


def test_un_servicio_de_una_solicitud_no_concretada_no_es_duplicado(
    cliente, crear_servicio, nuevo_vehiculo
):
    cerrada = crear_solicitud(
        cliente, estado_registro=EstadoRegistro.NO_CONCRETADA, motivo_no_concretada="precio"
    )
    crear_servicio(vehiculo=nuevo_vehiculo(placa="ABC123"), solicitud_de=cerrada)
    assert registro.duplicados_activos([registro.DatosVehiculo("ABC123", "")]) == []


def test_completar_un_borrador_no_se_advierte_a_si_mismo(client, logistica, con_telefono):
    solicitud = borrador_guardado(client, destino="")
    servicio = solicitud.servicios.get()
    client.post(ruta(solicitud, "completar/"), datos(servicio=str(servicio.pk)))
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA


# --- Regreso de eventos ------------------------------------------------------------------------


def evento(**cambios):
    return con_vehiculos(
        vehiculo("ABC123", referencia_externa="R-1"),
        vehiculo("XYZ789"),
        tipo="evento",
        **cambios,
    )


def test_evento_con_regreso_crea_por_vehiculo_el_servicio_de_regreso_enlazado(
    client, logistica, con_telefono
):
    respuesta = client.post(
        RUTA, evento(tiene_regreso="si", fecha_regreso="2026-11-22T18:00"), follow=True
    )
    solicitud = Solicitud.objects.get()
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA
    assert solicitud.tiene_regreso is True
    idas = list(solicitud.servicios.filter(regreso_de__isnull=True).order_by("pk"))
    assert len(idas) == 2
    for ida in idas:
        regreso = ida.regreso  # el enlace inverso del OneToOne
        assert regreso.solicitud == solicitud
        assert regreso.vehiculo == ida.vehiculo
        assert regreso.referencia_externa == ida.referencia_externa
        assert regreso.estado == E.PENDIENTE_ASIGNAR
    html = respuesta.content.decode()
    assert "Se crearon 2 servicios de regreso" in html
    assert f"Regreso del N.º {idas[0].pk} (destino a origen)" in html
    assert "del destino al origen" in html  # la fila Regreso del detalle


def test_evento_sin_regreso_queda_abierto_sin_servicios_de_regreso(client, logistica, con_telefono):
    client.post(RUTA, evento(tiene_regreso="no"))
    solicitud = Solicitud.objects.get()
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA
    assert solicitud.tiene_regreso is False
    assert not solicitud.servicios.filter(regreso_de__isnull=False).exists()


def test_evento_sin_responder_el_regreso_no_sale_de_borrador(client, logistica, con_telefono):
    respuesta = client.post(RUTA, evento(), follow=True)
    solicitud = Solicitud.objects.get()
    assert solicitud.estado_registro == EstadoRegistro.BORRADOR
    assert solicitud.tiene_regreso is None
    assert solicitud.servicios.count() == 2
    assert "la respuesta de si el evento tiene regreso" in respuesta.content.decode()


def test_regreso_sin_fecha_se_rechaza_junto_al_campo(client, logistica, con_telefono):
    respuesta = client.post(RUTA, evento(tiene_regreso="si"))
    html = respuesta.content.decode()
    assert "Escriba la fecha y la hora del regreso." in html
    assert html.index('name="fecha_regreso"') < html.index("Escriba la fecha y la hora del regreso.")
    assert Solicitud.objects.count() == 0


def test_evento_en_borrador_con_regreso_no_crea_regresos_hasta_abrirse(
    client, logistica, con_telefono
):
    client.post(RUTA, evento(tiene_regreso="si", fecha_regreso="2026-11-22T18:00", accion="borrador"))
    solicitud = Solicitud.objects.get()
    assert solicitud.estado_registro == EstadoRegistro.BORRADOR
    assert solicitud.servicios.count() == 2
    idas = list(solicitud.servicios.order_by("pk"))
    client.post(
        ruta(solicitud, "completar/"),
        con_vehiculos(
            vehiculo("ABC123", servicio=str(idas[0].pk)),
            vehiculo("XYZ789", servicio=str(idas[1].pk)),
            tipo="evento",
            tiene_regreso="si",
            fecha_regreso="2026-11-22T18:00",
        ),
    )
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA
    assert solicitud.servicios.filter(regreso_de__isnull=False).count() == 2
    assert solicitud.servicios.count() == 4


def test_fuera_de_un_evento_la_respuesta_de_regreso_no_se_guarda(client, logistica, con_telefono):
    client.post(RUTA, datos(tiene_regreso="si", fecha_regreso="2026-11-22T18:00"))
    solicitud = Solicitud.objects.get()
    assert (solicitud.tiene_regreso, solicitud.fecha_regreso) == (None, None)
    assert solicitud.servicios.count() == 1


def test_un_servicio_de_regreso_tambien_se_asigna(client, logistica, con_telefono, ana):
    client.post(RUTA, evento(tiene_regreso="si", fecha_regreso="2026-11-22T18:00"))
    regreso = Servicio.objects.filter(regreso_de__isnull=False).first()
    operaciones.asignar(regreso, ana, actor=logistica)
    assert regreso.estado == E.ASIGNADO


# --- No concretada -----------------------------------------------------------------------------


def cerrar(client, solicitud, **campos):
    return client.post(ruta(solicitud, "no-concretada/"), campos, follow=True)


def test_cerrar_un_borrador_como_no_concretada(client, logistica, con_telefono):
    solicitud = borrador_guardado(client)
    respuesta = cerrar(client, solicitud, motivo="precio", detalle=" Le pareció caro ")
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.NO_CONCRETADA
    assert (solicitud.motivo_no_concretada, solicitud.detalle_no_concretada) == (
        "precio",
        "Le pareció caro",
    )
    html = respuesta.content.decode()
    assert "cerrada como no concretada" in html
    assert "Precio. Le pareció caro" in html
    assert "Completar borrador" not in html


def test_cerrar_una_abierta_sin_asignar_no_cancela_sus_servicios(client, logistica, con_telefono):
    client.post(RUTA, datos())
    solicitud = Solicitud.objects.get()
    cerrar(client, solicitud, motivo="sin_grua")
    solicitud.refresh_from_db()
    assert solicitud.estado == "no_concretada"
    # "No concretada" es de la solicitud y es distinto de "Cancelado".
    assert solicitud.servicios.get().estado == E.PENDIENTE_ASIGNAR
    assert not EventoEstado.objects.exists()


def test_cerrar_sin_motivo_marca_el_campo_y_no_cierra(client, logistica, con_telefono):
    solicitud = borrador_guardado(client)
    respuesta = client.post(ruta(solicitud, "no-concretada/"), {"motivo": ""})
    assert respuesta.status_code == 200
    assert "Elija el motivo por el que no se concretó." in respuesta.content.decode()
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.BORRADOR


def test_cerrar_por_get_no_esta_permitido(client, logistica, cliente):
    solicitud = crear_solicitud(cliente)
    assert client.get(ruta(solicitud, "no-concretada/")).status_code == 405


def test_con_un_servicio_asignado_no_se_ofrece_ni_se_cierra(
    client, logistica, solicitud, crear_servicio
):
    crear_servicio(E.ASIGNADO)
    assert "Cerrar como no concretada" not in client.get(ruta(solicitud)).content.decode()
    respuesta = cerrar(client, solicitud, motivo="precio")
    assert "No se cerró" in respuesta.content.decode()
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA


def test_un_servicio_que_se_asigno_y_volvio_a_la_cola_impide_cerrar(
    solicitud, crear_servicio, ana, usuario
):
    servicio = crear_servicio()
    operaciones.asignar(servicio, ana, actor=usuario)
    operaciones.cambiar_estado(servicio, E.CANCELADO, actor=usuario, motivo="Cliente desistió")
    assert registro.puede_cerrarse_no_concretada(solicitud) is False
    with pytest.raises(CierreNoPermitido):
        registro.cerrar_no_concretada(solicitud, motivo="desistio")


def test_la_opcion_de_cerrar_aparece_sin_servicios_asignados(client, logistica, solicitud, crear_servicio):
    crear_servicio()
    html = client.get(ruta(solicitud)).content.decode()
    assert "Cerrar como no concretada" in html
    assert 'action="/solicitudes/' in html


def test_una_no_concretada_no_se_vuelve_a_cerrar(cliente):
    solicitud = crear_solicitud(
        cliente, estado_registro=EstadoRegistro.NO_CONCRETADA, motivo_no_concretada="precio"
    )
    assert registro.puede_cerrarse_no_concretada(solicitud) is False
    with pytest.raises(CierreNoPermitido):
        registro.cerrar_no_concretada(solicitud, motivo="otro")


def test_despues_de_cerrarla_sus_servicios_no_se_asignan(solicitud, crear_servicio, ana, usuario):
    servicio = crear_servicio()
    registro.cerrar_no_concretada(solicitud, motivo="demora")
    with pytest.raises(SolicitudNoAsignable, match="no se concretó"):
        operaciones.asignar(servicio, ana, actor=usuario)


def test_un_evento_abierto_sin_respuesta_de_regreso_se_puede_cerrar(cliente):
    # La base no exige la respuesta de regreso a un evento no concretado.
    solicitud = crear_solicitud(cliente, tipo="evento", estado_registro=EstadoRegistro.BORRADOR)
    registro.cerrar_no_concretada(solicitud, motivo="desistio")
    solicitud.refresh_from_db()
    assert solicitud.estado_registro == EstadoRegistro.NO_CONCRETADA
