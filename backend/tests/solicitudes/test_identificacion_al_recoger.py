"""Placa o VIN digitados por el conductor al recoger (1a-13b), contra PostgreSQL.

El Recogido trae lo que el conductor digitó porque el vehículo llegó sin placa ni VIN. Si el
vehículo no tiene ese dato, se guarda en él; si ya tiene otro, no se sobreescribe. Lo físico nunca
se rechaza: el Recogido se aplica igual y lo digitado queda en el evento. Lo que no encaja (dato
distinto, inválido o de otro vehículo) abre una alerta a logística sin tumbar el evento ni el lote.
"""
import pytest

from alertas.models import Alerta, TipoAlerta
from alertas.operaciones import resolver_alerta
from nucleo.estados import Estado
from nucleo.sincronizacion import Motivo, Resultado
from nucleo.tipos import TipoServicio
from solicitudes import operaciones
from solicitudes.models import EventoEstado, Vehiculo
from solicitudes.operaciones import aplicar_evento_del_conductor, sincronizar_lote_del_conductor

from ..conftest import VIN, crear_solicitud

pytestmark = pytest.mark.django_db

E = Estado
APLICADO, DUPLICADO, CONFLICTO = Resultado.APLICADO, Resultado.DUPLICADO, Resultado.CONFLICTO
OTRO_VIN = "WVWZZZ1JZXW000001"


def identificacion(vehiculo) -> tuple[str, str]:
    vehiculo.refresh_from_db()
    return vehiculo.placa, vehiculo.vin


def estado_de(servicio):
    servicio.refresh_from_db()
    return servicio.estado


def guardado(datos) -> EventoEstado:
    return EventoEstado.objects.get(pk=datos["id"])


def alertas_por_revisar(datos):
    return Alerta.objects.filter(
        tipo=TipoAlerta.IDENTIFICACION_POR_REVISAR, registro_id=str(datos["id"])
    )


@pytest.fixture
def sin_identificar(nuevo_vehiculo):
    return nuevo_vehiculo(placa="", vin="", marca="Mazda", linea="CX-30")


@pytest.fixture
def por_recoger(crear_servicio, sin_identificar):
    """Un servicio en camino cuyo vehículo no tiene placa ni VIN."""
    return crear_servicio(E.EN_CAMINO, vehiculo=sin_identificar)


# --- Lo digitado completa el vehículo ----------------------------------------------------------


def test_recogido_con_placa_digitada_la_guarda_en_el_vehiculo(
    por_recoger, sin_identificar, evento_app
):
    datos = evento_app(por_recoger, E.RECOGIDO, placa="abc-123")

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert estado_de(por_recoger) == E.RECOGIDO
    assert identificacion(sin_identificar) == ("ABC123", "")
    evento = guardado(datos)
    assert (evento.placa_digitada, evento.vin_digitado) == ("ABC123", "")
    assert evento.resultado == EventoEstado.Resultado.APLICADO
    assert not Alerta.objects.exists()


def test_recogido_con_vin_digitado_lo_guarda_normalizado(por_recoger, sin_identificar, evento_app):
    datos = evento_app(por_recoger, E.RECOGIDO, vin="1hg-cm826 33a004352")

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert identificacion(sin_identificar) == ("", VIN)
    assert guardado(datos).vin_digitado == VIN


def test_recogido_con_placa_y_vin_digitados_guarda_los_dos(
    por_recoger, sin_identificar, evento_app
):
    datos = evento_app(por_recoger, E.RECOGIDO, placa="ABC123", vin=VIN)
    assert aplicar_evento_del_conductor(**datos) == APLICADO
    assert identificacion(sin_identificar) == ("ABC123", VIN)


def test_un_desvare_con_vin_y_sin_placa_se_recoge_con_la_placa_digitada(
    cliente, crear_servicio, nuevo_vehiculo, evento_app
):
    vehiculo = nuevo_vehiculo(placa="", vin=VIN)
    desvare = crear_solicitud(cliente, tipo=TipoServicio.DESVARE)
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=vehiculo, solicitud_de=desvare)

    assert aplicar_evento_del_conductor(**evento_app(servicio, E.RECOGIDO, placa="ABC123")) == (
        APLICADO
    )

    assert identificacion(vehiculo) == ("ABC123", VIN)


def test_lo_digitado_igual_a_lo_que_tiene_el_vehiculo_no_cambia_nada_ni_alerta(
    crear_servicio, nuevo_vehiculo, evento_app
):
    vehiculo = nuevo_vehiculo(placa="ABC123", vin=VIN)
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=vehiculo)
    datos = evento_app(servicio, E.RECOGIDO, placa="abc 123", vin=VIN.lower())

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert identificacion(vehiculo) == ("ABC123", VIN)
    assert not Alerta.objects.exists()


def test_un_vehiculo_con_placa_recibe_el_vin_digitado(crear_servicio, nuevo_vehiculo, evento_app):
    vehiculo = nuevo_vehiculo(placa="ABC123")
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=vehiculo)
    assert aplicar_evento_del_conductor(**evento_app(servicio, E.RECOGIDO, vin=VIN)) == APLICADO
    assert identificacion(vehiculo) == ("ABC123", VIN)


# --- Lo que no encaja: se aplica igual y abre una alerta ---------------------------------------


def test_recogido_con_placa_distinta_a_la_existente_no_la_sobreescribe_y_abre_alerta(
    crear_servicio, nuevo_vehiculo, evento_app
):
    vehiculo = nuevo_vehiculo(placa="ABC123", marca="Mazda")
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=vehiculo)
    datos = evento_app(servicio, E.RECOGIDO, placa="XYZ789")

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert estado_de(servicio) == E.RECOGIDO
    assert identificacion(vehiculo) == ("ABC123", "")
    assert guardado(datos).placa_digitada == "XYZ789"
    (alerta,) = alertas_por_revisar(datos)
    assert alerta.registro == guardado(datos)
    assert "digitó la placa XYZ789, pero el vehículo ya tenía ABC123" in alerta.mensaje
    assert "El Recogido se aplicó" in alerta.mensaje


def test_recogido_con_vin_distinto_al_existente_no_lo_sobreescribe_y_abre_alerta(
    crear_servicio, nuevo_vehiculo, evento_app
):
    vehiculo = nuevo_vehiculo(placa="", vin=VIN)
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=vehiculo)
    datos = evento_app(servicio, E.RECOGIDO, vin=OTRO_VIN)

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert identificacion(vehiculo) == ("", VIN)
    assert f"el VIN {OTRO_VIN}, pero el vehículo ya tenía {VIN}" in (
        alertas_por_revisar(datos).get().mensaje
    )


def test_recogido_con_placa_de_otro_vehiculo_se_aplica_sin_guardarla_y_abre_alerta(
    por_recoger, sin_identificar, nuevo_vehiculo, evento_app
):
    nuevo_vehiculo(placa="ABC123", marca="Renault", linea="Logan")
    datos = evento_app(por_recoger, E.RECOGIDO, placa="ABC123")

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert estado_de(por_recoger) == E.RECOGIDO
    assert identificacion(sin_identificar) == ("", "")
    assert Vehiculo.objects.filter(placa="ABC123").count() == 1
    assert guardado(datos).placa_digitada == "ABC123"
    mensaje = alertas_por_revisar(datos).get().mensaje
    assert "la placa ABC123, que ya es de otro vehículo (ABC123 · Renault Logan)" in mensaje


def test_recogido_con_vin_de_otro_vehiculo_guarda_la_placa_y_alerta_por_el_vin(
    por_recoger, sin_identificar, nuevo_vehiculo, evento_app
):
    nuevo_vehiculo(placa="OTR111", vin=VIN)
    datos = evento_app(por_recoger, E.RECOGIDO, placa="ABC123", vin=VIN)

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert identificacion(sin_identificar) == ("ABC123", "")
    mensaje = alertas_por_revisar(datos).get().mensaje
    assert f"el VIN {VIN}, que ya es de otro vehículo (OTR111" in mensaje
    assert "placa ABC123" not in mensaje.split("pero el conductor")[1]


@pytest.mark.parametrize(
    ("digitado", "texto"),
    [
        ({"vin": VIN[:16]}, f"el VIN '{VIN[:16]}', que no es válido (17 letras o dígitos"),
        ({"vin": VIN[:-1] + "O"}, "que no es válido (17 letras o dígitos, sin I, O ni Q)"),
        ({"placa": "ABC-DEF-GHI-JK"}, "la placa 'ABCDEFGHIJK', que no es válido (de 1 a 10"),
    ],
)
def test_recogido_con_dato_invalido_se_aplica_sin_guardarlo_y_abre_alerta(
    por_recoger, sin_identificar, evento_app, digitado, texto
):
    datos = evento_app(por_recoger, E.RECOGIDO, **digitado)

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert estado_de(por_recoger) == E.RECOGIDO
    assert identificacion(sin_identificar) == ("", "")
    assert texto in alertas_por_revisar(datos).get().mensaje


def test_varios_datos_por_revisar_van_en_una_sola_alerta(
    crear_servicio, nuevo_vehiculo, evento_app
):
    vehiculo = nuevo_vehiculo(placa="ABC123")
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=vehiculo)
    datos = evento_app(servicio, E.RECOGIDO, placa="XYZ789", vin="MALO")

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    (alerta,) = Alerta.objects.all()
    assert "la placa XYZ789" in alerta.mensaje and "el VIN 'MALO'" in alerta.mensaje


def test_la_alerta_de_identificacion_convive_con_la_de_capacidad(
    crear_servicio, por_recoger, nuevo_vehiculo, evento_app
):
    crear_servicio(E.RECOGIDO)  # la grúa de Ana (un puesto) ya va llena
    nuevo_vehiculo(placa="ABC123")
    datos = evento_app(por_recoger, E.RECOGIDO, placa="ABC123")

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert guardado(datos).capacidad_excedida is True
    assert set(Alerta.objects.values_list("tipo", flat=True)) == {
        TipoAlerta.CAPACIDAD_EXCEDIDA,
        TipoAlerta.IDENTIFICACION_POR_REVISAR,
    }


# --- Sin identificación ni digitada: sigue siendo conflicto -------------------------------------


@pytest.mark.parametrize("digitada", [{}, {"placa": None, "vin": None}, {"placa": " - "}])
def test_recogido_sin_nada_digitado_sigue_siendo_conflicto_por_identificacion(
    por_recoger, evento_app, digitada
):
    datos = evento_app(por_recoger, E.RECOGIDO, **digitada)

    assert aplicar_evento_del_conductor(**datos) == CONFLICTO

    assert estado_de(por_recoger) == E.EN_CAMINO
    assert guardado(datos).motivo_conflicto == Motivo.IDENTIFICACION_INCOMPLETA
    assert not alertas_por_revisar(datos).exists()


def test_un_desvare_con_solo_el_vin_digitado_es_conflicto_y_no_toca_el_vehiculo(
    cliente, crear_servicio, sin_identificar, evento_app
):
    desvare = crear_solicitud(cliente, tipo=TipoServicio.DESVARE)
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=sin_identificar, solicitud_de=desvare)
    datos = evento_app(servicio, E.RECOGIDO, vin=VIN)

    assert aplicar_evento_del_conductor(**datos) == CONFLICTO

    assert identificacion(sin_identificar) == ("", "")
    assert guardado(datos).vin_digitado == VIN  # queda en el evento
    alerta = Alerta.objects.get(tipo=TipoAlerta.CONFLICTO_SINCRONIZACION)
    assert "Al vehículo le falta la placa o el VIN para recogerlo." in alerta.mensaje
    assert f"Al recogerlo digitó el VIN {VIN}." in alerta.mensaje


def test_un_recogido_en_conflicto_guarda_lo_digitado_en_el_evento_y_no_toca_el_vehiculo(
    crear_servicio, sin_identificar, evento_app
):
    servicio = crear_servicio(E.ASIGNADO, vehiculo=sin_identificar)  # falta marcar En camino
    datos = evento_app(servicio, E.RECOGIDO, placa="ABC123")

    assert aplicar_evento_del_conductor(**datos) == CONFLICTO

    assert guardado(datos).motivo_conflicto == Motivo.SALTO_DE_ESTADO
    assert guardado(datos).placa_digitada == "ABC123"
    assert identificacion(sin_identificar) == ("", "")
    assert "Al recogerlo digitó la placa ABC123." in Alerta.objects.get().mensaje


def test_en_otro_destino_la_placa_y_el_vin_se_ignoran(
    crear_servicio, sin_identificar, evento_app
):
    servicio = crear_servicio(E.ASIGNADO, vehiculo=sin_identificar)
    datos = evento_app(servicio, E.EN_CAMINO, placa="ABC123", vin=VIN)

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    evento = guardado(datos)
    assert (evento.placa_digitada, evento.vin_digitado) == ("", "")
    assert identificacion(sin_identificar) == ("", "")


# --- Reenvíos y lotes ----------------------------------------------------------------------------


def test_el_duplicado_del_evento_no_repite_efectos(por_recoger, sin_identificar, evento_app):
    datos = evento_app(por_recoger, E.RECOGIDO, placa="ABC123")
    assert aplicar_evento_del_conductor(**datos) == APLICADO

    # Logística corrige la placa en el admin; el reenvío del mismo toque no la vuelve a pisar.
    Vehiculo.objects.filter(pk=sin_identificar.pk).update(placa="ABC124")
    assert aplicar_evento_del_conductor(**datos) == DUPLICADO
    assert aplicar_evento_del_conductor(**{**datos, "placa": "XYZ789"}) == DUPLICADO

    assert identificacion(sin_identificar) == ("ABC124", "")
    assert EventoEstado.objects.filter(servicio=por_recoger).count() == 1
    assert not Alerta.objects.exists()


def test_el_duplicado_no_vuelve_a_abrir_la_alerta_resuelta(
    por_recoger, nuevo_vehiculo, evento_app, usuario
):
    nuevo_vehiculo(placa="ABC123")
    datos = evento_app(por_recoger, E.RECOGIDO, placa="ABC123")
    assert aplicar_evento_del_conductor(**datos) == APLICADO
    resolver_alerta(alertas_por_revisar(datos).get(), por=usuario)

    assert aplicar_evento_del_conductor(**datos) == DUPLICADO

    assert not alertas_por_revisar(datos).filter(resuelta_en__isnull=True).exists()
    assert alertas_por_revisar(datos).count() == 1


def test_el_choque_con_otro_vehiculo_no_rompe_el_lote(
    crear_servicio, por_recoger, sin_identificar, nuevo_vehiculo, evento_app
):
    nuevo_vehiculo(placa="ABC123")
    otro = crear_servicio(E.ASIGNADO)
    lote = [
        evento_app(por_recoger, E.RECOGIDO, secuencia=1, placa="ABC123"),
        evento_app(otro, E.EN_CAMINO, secuencia=2),
        evento_app(por_recoger, E.ENTREGADO, secuencia=3, nombre_quien="Marta"),
    ]

    resultados = sincronizar_lote_del_conductor(lote)

    assert [a.resultado for a in resultados] == [APLICADO] * 3
    assert (estado_de(por_recoger), estado_de(otro)) == (E.ENTREGADO, E.EN_CAMINO)
    assert identificacion(sin_identificar) == ("", "")
    assert alertas_por_revisar(lote[0]).count() == 1


def test_si_la_base_rechaza_la_placa_por_unicidad_el_evento_sigue_en_su_transaccion(
    monkeypatch, por_recoger, sin_identificar, nuevo_vehiculo, evento_app
):
    # Como si otro evento hubiera guardado la placa justo después de la consulta previa: el UPDATE
    # choca con la restricción de unicidad dentro de la transacción del evento. El punto de
    # restauración deshace solo ese cambio; el Recogido, el VIN y la alerta quedan.
    otro = nuevo_vehiculo(placa="ABC123")
    consultas = []

    def sin_ver_al_otro(campo, dato, *, excepto):
        consultas.append(campo)
        if len(consultas) == 1:
            return None
        return Vehiculo.objects.filter(**{campo.value: dato}).exclude(pk=excepto).first()

    monkeypatch.setattr(operaciones, "_vehiculo_con", sin_ver_al_otro)
    datos = evento_app(por_recoger, E.RECOGIDO, placa="ABC123", vin=VIN)

    assert aplicar_evento_del_conductor(**datos) == APLICADO

    assert estado_de(por_recoger) == E.RECOGIDO
    assert identificacion(sin_identificar) == ("", VIN)
    assert identificacion(otro) == ("ABC123", "")
    assert f"la placa ABC123, que ya es de otro vehículo ({otro})" in (
        alertas_por_revisar(datos).get().mensaje
    )


def test_otro_error_de_la_base_al_completar_el_vehiculo_no_se_esconde(
    monkeypatch, por_recoger, sin_identificar, evento_app
):
    # Una falla que no es la unicidad tumba solo ese evento (la app lo reenvía): nada queda.
    def falla(*args, **kwargs):
        raise RuntimeError("la base se cayó")

    monkeypatch.setattr(operaciones, "completar_identificacion", falla)
    datos = evento_app(por_recoger, E.RECOGIDO, placa="ABC123")

    (aplicacion,) = sincronizar_lote_del_conductor([datos])

    assert (aplicacion.resultado, aplicacion.motivo) == (
        Resultado.REINTENTAR,
        Motivo.ERROR_DEL_SERVIDOR,
    )
    assert estado_de(por_recoger) == E.EN_CAMINO
    assert not EventoEstado.objects.exists()
    assert identificacion(sin_identificar) == ("", "")
