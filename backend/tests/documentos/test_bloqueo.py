"""Documento vencido contra PostgreSQL: bloquea asignaciones nuevas (asignar y reasignar) del
conductor con documento vencido o cuya grúa vigente lo tenga; no interrumpe un servicio en curso
(los eventos del conductor y los cambios de estado siguen)."""
import pytest

from nucleo.estados import Estado, Resolucion
from nucleo.sincronizacion import Resultado
from solicitudes import operaciones
from solicitudes.disponibilidad import disponibilidad_de_conductores, motivos_de_bloqueo
from solicitudes.operaciones import ConductorBloqueado
from tests.api.conftest import enviar, evento_json

pytestmark = pytest.mark.django_db

E = Estado


def de(conductor):
    return next(d for d in disponibilidad_de_conductores() if d.conductor == conductor)


# --- Bloquea lo nuevo ----------------------------------------------------------------------------


def test_conductor_con_licencia_vencida_no_es_asignable(
    licencia, ana, crear_servicio, registrar, usuario
):
    registrar(licencia, ana, vence_en=-1)
    servicio = crear_servicio(E.PENDIENTE_ASIGNAR)

    assert motivos_de_bloqueo(ana) == ["Documento vencido: Licencia de conducción de Ana."]
    with pytest.raises(ConductorBloqueado, match="Licencia de conducción de Ana"):
        operaciones.asignar(servicio, ana, actor=usuario)
    servicio.refresh_from_db()
    assert servicio.estado == E.PENDIENTE_ASIGNAR
    assert servicio.conductor is None


def test_grua_con_soat_vencido_bloquea_a_su_conductor(soat, ana, grua1, crear_servicio,
                                                      registrar, usuario):
    registrar(soat, grua1, vence_en=-1)
    servicio = crear_servicio(E.PENDIENTE_ASIGNAR)

    with pytest.raises(ConductorBloqueado, match="SOAT de la grúa GRU001"):
        operaciones.asignar(servicio, ana, actor=usuario)


def test_reasignar_a_un_conductor_con_documento_vencido_se_rechaza(
    soat, ana, beto, grua2, crear_servicio, registrar, usuario
):
    servicio = crear_servicio(E.ASIGNADO, conductor=ana)
    registrar(soat, grua2, vence_en=-3)

    with pytest.raises(ConductorBloqueado, match="SOAT de la grúa GRU002"):
        operaciones.reasignar(servicio, beto, actor=usuario)
    servicio.refresh_from_db()
    assert servicio.conductor == ana


def test_la_lista_de_conductores_muestra_bloqueado_con_el_documento_vencido(
    soat, ana, beto, grua1, registrar
):
    registrar(soat, grua1, vence_en=-1)
    assert de(ana).bloqueado
    assert de(ana).motivos == ("Documento vencido: SOAT de la grúa GRU001.",)
    assert not de(beto).bloqueado


def test_documento_que_vence_hoy_no_bloquea(licencia, ana, crear_servicio, registrar, usuario):
    registrar(licencia, ana, vence_en=0)
    servicio = crear_servicio(E.PENDIENTE_ASIGNAR)
    operaciones.asignar(servicio, ana, actor=usuario)
    assert servicio.conductor == ana


def test_aun_no_aplica_no_bloquea(tecnomecanica, ana, grua1, crear_servicio, registrar, usuario):
    registrar(tecnomecanica, grua1, aplica_desde_en=30)
    servicio = crear_servicio(E.PENDIENTE_ASIGNAR)
    operaciones.asignar(servicio, ana, actor=usuario)
    assert servicio.estado == E.ASIGNADO


def test_documento_que_falta_no_bloquea(ana):
    # Sin ningún documento registrado: la regla escrita solo bloquea por vencido (QUESTIONS.md).
    assert motivos_de_bloqueo(ana) == []
    assert not de(ana).bloqueado


def test_renovar_el_documento_desbloquea(licencia, ana, crear_servicio, registrar, usuario):
    registrar(licencia, ana, vence_en=-1)
    registrar(licencia, ana, vence_en=365)
    servicio = crear_servicio(E.PENDIENTE_ASIGNAR)
    operaciones.asignar(servicio, ana, actor=usuario)
    assert servicio.conductor == ana


# --- No interrumpe lo que está en curso ----------------------------------------------------------


def test_servicio_en_curso_sigue_recibiendo_eventos_del_conductor_con_documento_vencido(
    licencia, soat, ana, grua1, crear_servicio, evento_app, registrar
):
    servicio = crear_servicio(E.ASIGNADO, conductor=ana)
    registrar(licencia, ana, vence_en=-1)
    registrar(soat, grua1, vence_en=-1)

    for secuencia, destino in enumerate((E.EN_CAMINO, E.RECOGIDO, E.ENTREGADO), start=1):
        resultado = operaciones.aplicar_evento_del_conductor(
            **evento_app(servicio, destino, secuencia=secuencia)
        )
        assert resultado == Resultado.APLICADO
    servicio.refresh_from_db()
    assert servicio.estado == E.ENTREGADO


def test_servicio_en_curso_sigue_recibiendo_eventos_por_la_api_con_documento_vencido(
    sesion, licencia, ana, crear_servicio, registrar
):
    servicio = crear_servicio(E.ASIGNADO, conductor=ana)
    registrar(licencia, ana, vence_en=-1)

    resultados = enviar(sesion, evento_json(servicio, E.EN_CAMINO, secuencia=1))

    assert resultados[0]["resultado"] == "aplicado"
    servicio.refresh_from_db()
    assert servicio.estado == E.EN_CAMINO


def test_cambios_de_estado_desde_el_panel_siguen_con_documento_vencido(
    licencia, ana, crear_servicio, registrar, usuario
):
    servicio = crear_servicio(E.EN_CAMINO, conductor=ana)
    registrar(licencia, ana, vence_en=-1)

    operaciones.cambiar_estado(servicio, E.NOVEDAD, actor=usuario, motivo="Llanta pinchada")
    operaciones.resolver_novedad(servicio, Resolucion.REANUDAR, actor=usuario)
    operaciones.cambiar_estado(servicio, E.RECOGIDO, actor=usuario)
    operaciones.cambiar_estado(servicio, E.ENTREGADO, actor=usuario)

    servicio.refresh_from_db()
    assert servicio.estado == E.ENTREGADO
