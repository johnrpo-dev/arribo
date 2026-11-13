"""`POST /api/v1/eventos/`: lotes de toques del conductor contra PostgreSQL.

Idempotentes por el id del celular, ordenados por secuencia, nunca descartados: lo que no encaja se
guarda como conflicto con su motivo y abre una alerta a logística. Cada evento es atómico con sus
efectos y uno malo no tumba los demás.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from alertas.models import Alerta, TipoAlerta
from clientes.models import Cliente, Tarifa, TipoCliente
from cobros import operaciones as cobro
from cobros.models import LineaCobro
from nucleo.estados import Estado
from nucleo.tipos import TipoServicio
from solicitudes import operaciones
from solicitudes.models import EventoEstado, OrigenEvento, ResultadoEvento

from ..conftest import crear_solicitud
from .conftest import URL_EVENTOS, enviar, evento_json
from .test_asignaciones import FRAGMENTOS_DE_COBRO, _claves

pytestmark = pytest.mark.django_db

E = Estado


def estado_de(servicio):
    servicio.refresh_from_db()
    return servicio.estado


def guardado(evento) -> EventoEstado:
    return EventoEstado.objects.get(pk=evento["id"])


def alertas_de(evento, tipo=TipoAlerta.CONFLICTO_SINCRONIZACION):
    return Alerta.objects.filter(tipo=tipo, registro_id=str(evento["id"]))


def en_su_ronda(servicio, estado, *, previo=None, montado=False) -> dict:
    return {
        "id": servicio.pk,
        "estado": estado,
        "estado_previo": previo,
        "a_bordo": montado,
        "en_su_ronda": True,
    }


def fuera_de_su_ronda(servicio, estado=None) -> dict:
    return {
        "id": servicio.pk,
        "estado": estado,
        "estado_previo": None,
        "a_bordo": False,
        "en_su_ronda": False,
    }


# --- Evento válido -------------------------------------------------------------------------------


def test_un_evento_valido_se_aplica_y_la_respuesta_trae_el_estado_actual_del_servicio(
    sesion, ana, crear_servicio
):
    servicio = crear_servicio(E.ASIGNADO)
    evento = evento_json(servicio, E.EN_CAMINO, secuencia=118)

    respuesta = sesion.post(URL_EVENTOS, {"eventos": [evento]}, format="json")

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "version": 1,
        "resultados": [
            {
                "id": evento["id"],
                "resultado": "aplicado",
                "duplicado": False,
                "motivo": None,
                "detalle": None,
                "capacidad_excedida": False,
                "servicio": en_su_ronda(servicio, "en_camino"),
            }
        ],
    }
    assert estado_de(servicio) == E.EN_CAMINO
    fila = guardado(evento)
    assert (fila.origen, fila.resultado) == (OrigenEvento.APP, ResultadoEvento.APLICADO)
    assert (fila.conductor, fila.actor, fila.secuencia) == (ana, None, 118)
    assert not Alerta.objects.exists()


def test_se_guardan_la_hora_del_celular_y_la_hora_de_sincronizacion_del_servidor(
    sesion, crear_servicio, reloj
):
    servicio = crear_servicio(E.ASIGNADO)
    # El celular tiene el reloj atrasado un día: se guarda tal cual, junto a la hora del servidor.
    evento = evento_json(servicio, E.EN_CAMINO, hora_dispositivo="2026-11-19T08:42:07-05:00")

    enviar(sesion, evento)

    fila = guardado(evento)
    assert fila.hora_dispositivo == datetime(2026, 11, 19, 13, 42, 7, tzinfo=UTC)
    assert fila.hora_sincronizacion == reloj.ahora
    assert fila.hora_sincronizacion != fila.hora_dispositivo


def test_el_conductor_del_evento_es_el_del_token_y_no_un_campo_del_cuerpo(
    sesion, ana, beto, crear_servicio
):
    servicio = crear_servicio(E.ASIGNADO)
    evento = evento_json(servicio, E.EN_CAMINO, conductor=beto.pk, conductor_id=beto.pk)

    (resultado,) = enviar(sesion, evento)

    assert resultado["resultado"] == "aplicado"
    assert guardado(evento).conductor == ana


def test_recogido_y_entregado_guardan_quien_entrega_o_recibe_y_la_ubicacion(
    sesion, crear_servicio
):
    servicio = crear_servicio(E.EN_CAMINO)
    evento = evento_json(
        servicio, E.RECOGIDO, nombre_quien=" Portero Juan ", latitud=6.2442, longitud=-75.5812
    )

    (resultado,) = enviar(sesion, evento)

    assert resultado["servicio"] == en_su_ronda(servicio, "recogido", montado=True)
    fila = guardado(evento)
    assert (fila.nombre_quien, fila.latitud, fila.longitud) == ("Portero Juan", 6.2442, -75.5812)


def test_una_novedad_con_motivo_se_aplica_y_la_respuesta_trae_el_estado_previo(
    sesion, crear_servicio
):
    servicio = crear_servicio(E.RECOGIDO)
    evento = evento_json(servicio, E.NOVEDAD, motivo="El taller está cerrado")

    (resultado,) = enviar(sesion, evento)

    assert resultado["resultado"] == "aplicado"
    assert resultado["servicio"] == en_su_ronda(
        servicio, "novedad", previo="recogido", montado=True
    )
    assert guardado(evento).motivo == "El taller está cerrado"


# --- Idempotencia --------------------------------------------------------------------------------


def test_un_lote_repetido_no_se_aplica_dos_veces(sesion, crear_servicio):
    servicio = crear_servicio(E.ASIGNADO)
    lote = [
        evento_json(servicio, E.EN_CAMINO, secuencia=1),
        evento_json(servicio, E.RECOGIDO, secuencia=2, nombre_quien="Portero"),
        evento_json(servicio, E.ENTREGADO, secuencia=3, nombre_quien="Recepción"),
    ]

    primero = enviar(sesion, *lote)
    filas = list(EventoEstado.objects.order_by("secuencia").values())
    # El celular no recibió la respuesta (se cortó la señal) y reenvía el lote entero.
    segundo = enviar(sesion, *lote)

    assert [(r["resultado"], r["duplicado"]) for r in primero] == [("aplicado", False)] * 3
    assert [(r["resultado"], r["duplicado"]) for r in segundo] == [("aplicado", True)] * 3
    assert list(EventoEstado.objects.order_by("secuencia").values()) == filas
    assert len(filas) == 3
    assert estado_de(servicio) == E.ENTREGADO
    assert LineaCobro.objects.filter(servicio=servicio).count() == 1
    # Los dos envíos dicen lo mismo del servicio: ya entregado, fuera de la ronda.
    assert segundo[-1]["servicio"] == primero[-1]["servicio"] == fuera_de_su_ronda(
        servicio, "entregado"
    )


def test_el_mismo_evento_dos_veces_en_un_solo_lote_se_aplica_una_vez(sesion, crear_servicio):
    servicio = crear_servicio(E.ASIGNADO)
    evento = evento_json(servicio, E.EN_CAMINO)

    resultados = enviar(sesion, evento, dict(evento))

    assert [(r["resultado"], r["duplicado"]) for r in resultados] == [
        ("aplicado", False),
        ("aplicado", True),
    ]
    assert EventoEstado.objects.count() == 1


def test_un_duplicado_devuelve_el_resultado_original_y_un_conflicto_no_se_vuelve_a_evaluar(
    sesion, crear_servicio, usuario
):
    servicio = crear_servicio(E.ASIGNADO)
    salto = evento_json(servicio, E.RECOGIDO, secuencia=2)
    (primera,) = enviar(sesion, salto)
    # Logística avanza el servicio: ahora el mismo evento sí encajaría, pero ya se recibió.
    operaciones.cambiar_estado(servicio, E.EN_CAMINO, actor=usuario)

    (segunda,) = enviar(sesion, salto)

    assert (primera["resultado"], primera["duplicado"]) == ("conflicto", False)
    assert (segunda["resultado"], segunda["duplicado"]) == ("conflicto", True)
    assert segunda["motivo"] == primera["motivo"] == "salto_de_estado"
    assert segunda["detalle"] == primera["detalle"]
    assert estado_de(servicio) == E.EN_CAMINO
    assert segunda["servicio"] == en_su_ronda(servicio, "en_camino")
    assert servicio.eventos.filter(origen=OrigenEvento.APP).count() == 1
    assert alertas_de(salto).count() == 1  # el reenvío no abre otra alerta


def test_el_duplicado_de_un_recogido_sobre_capacidad_conserva_la_marca(sesion, crear_servicio):
    crear_servicio(E.RECOGIDO)
    servicio = crear_servicio(E.EN_CAMINO)
    evento = evento_json(servicio, E.RECOGIDO)
    enviar(sesion, evento)

    (repetido,) = enviar(sesion, evento)

    assert (repetido["resultado"], repetido["duplicado"]) == ("aplicado", True)
    assert repetido["capacidad_excedida"] is True


# --- Mismo id con otro contenido -----------------------------------------------------------------


@pytest.mark.parametrize("cambio", ["servicio", "destino", "secuencia"])
def test_el_mismo_id_con_otro_contenido_se_rechaza_sin_aplicar_ni_pisar_el_guardado(
    sesion, ana, crear_servicio, cambio
):
    servicio, otro = crear_servicio(E.ASIGNADO), crear_servicio(E.ASIGNADO)
    original = evento_json(servicio, E.EN_CAMINO, secuencia=5)
    enviar(sesion, original)
    distinto = {
        "servicio": {**original, "servicio_id": otro.pk},
        "destino": {**original, "destino": "recogido"},
        "secuencia": {**original, "secuencia": 6},
    }[cambio]

    (resultado,) = enviar(sesion, distinto)

    assert (resultado["resultado"], resultado["duplicado"]) == ("rechazado", False)
    assert resultado["motivo"] == "id_reutilizado"
    assert resultado["detalle"] == "Ese id ya se usó en un evento distinto."
    assert EventoEstado.objects.count() == 1  # ni se guarda como conflicto nuevo
    fila = guardado(original)
    assert (fila.servicio, fila.destino, fila.secuencia) == (servicio, "en_camino", 5)
    assert (estado_de(servicio), estado_de(otro)) == (E.EN_CAMINO, E.ASIGNADO)
    # Lo que llegó no se pierde en silencio: logística lo ve en una alerta sobre el evento original.
    alerta = alertas_de(original, TipoAlerta.EVENTO_RECHAZADO).get()
    assert "Ese id ya se usó en un evento distinto." in alerta.mensaje
    assert str(distinto["secuencia"]) in alerta.mensaje
    # Reintentar el mismo rechazado no multiplica las alertas.
    enviar(sesion, distinto)
    assert Alerta.objects.count() == 1


def test_el_id_de_un_evento_de_otro_conductor_no_se_puede_reutilizar(
    sesion, sesion_beto, crear_servicio
):
    servicio = crear_servicio(E.ASIGNADO)
    evento = evento_json(servicio, E.EN_CAMINO)
    enviar(sesion, evento)

    (resultado,) = enviar(sesion_beto, evento)

    assert (resultado["resultado"], resultado["motivo"]) == ("rechazado", "id_reutilizado")
    assert resultado["servicio"] == fuera_de_su_ronda(servicio)  # a Beto no se le dice el estado
    assert EventoEstado.objects.count() == 1


# --- Conflictos: se guardan, no cambian el servicio y abren alerta -------------------------------


def test_evento_sobre_servicio_cancelado_es_conflicto_guardado_con_alerta(
    sesion, ana, crear_servicio, usuario
):
    servicio = crear_servicio(E.ASIGNADO)
    operaciones.cambiar_estado(servicio, E.CANCELADO, actor=usuario, motivo="El cliente desistió")
    evento = evento_json(servicio, E.EN_CAMINO)

    (resultado,) = enviar(sesion, evento)

    assert (resultado["resultado"], resultado["motivo"]) == ("conflicto", "servicio_cancelado")
    assert resultado["detalle"] == "El servicio ya estaba cancelado."
    # La app lo muestra como cancelado y lo saca de la lista.
    assert resultado["servicio"] == fuera_de_su_ronda(servicio, "cancelado")
    assert estado_de(servicio) == E.CANCELADO
    fila = guardado(evento)
    assert (fila.resultado, fila.motivo_conflicto) == (
        ResultadoEvento.CONFLICTO,
        "servicio_cancelado",
    )
    assert (fila.destino, fila.conductor) == ("en_camino", ana)
    alerta = alertas_de(evento).get()
    assert alerta.abierta and alerta.registro == fila
    assert "Ana marcó En camino" in alerta.mensaje
    assert "El servicio ya estaba cancelado." in alerta.mensaje


def test_evento_sobre_servicio_reasignado_es_conflicto_y_no_revela_el_estado(
    sesion, ana, beto, crear_servicio, usuario
):
    servicio = crear_servicio(E.ASIGNADO)
    operaciones.reasignar(servicio, beto, actor=usuario)
    evento = evento_json(servicio, E.EN_CAMINO)  # Ana, sin señal, no se enteró

    (resultado,) = enviar(sesion, evento)

    assert (resultado["resultado"], resultado["motivo"]) == ("conflicto", "servicio_no_asignado")
    assert resultado["servicio"] == fuera_de_su_ronda(servicio)  # desaparece de su lista
    servicio.refresh_from_db()
    assert (servicio.estado, servicio.conductor) == (E.ASIGNADO, beto)
    assert guardado(evento).conductor == ana
    assert alertas_de(evento).count() == 1


def test_evento_sobre_un_servicio_que_nunca_fue_suyo_es_conflicto_guardado(
    sesion, ana, beto, crear_servicio
):
    ajeno = crear_servicio(E.ASIGNADO, conductor=beto)
    evento = evento_json(ajeno, E.EN_CAMINO)

    (resultado,) = enviar(sesion, evento)

    assert (resultado["resultado"], resultado["motivo"]) == ("conflicto", "servicio_no_asignado")
    assert resultado["servicio"] == fuera_de_su_ronda(ajeno)
    assert estado_de(ajeno) == E.ASIGNADO
    fila = guardado(evento)
    assert (fila.resultado, fila.conductor) == (ResultadoEvento.CONFLICTO, ana)
    assert alertas_de(evento).count() == 1


@pytest.mark.parametrize(
    ("origen", "destino"),
    [
        (E.ASIGNADO, E.RECOGIDO),
        (E.ASIGNADO, E.ENTREGADO),
        (E.EN_CAMINO, E.ENTREGADO),
        (E.RECOGIDO, E.EN_CAMINO),
        (E.EN_CAMINO, E.EN_CAMINO),
    ],
)
def test_un_salto_o_retroceso_de_estado_es_conflicto_guardado_con_alerta(
    sesion, crear_servicio, origen, destino
):
    servicio = crear_servicio(origen)
    evento = evento_json(servicio, destino)

    (resultado,) = enviar(sesion, evento)

    assert (resultado["resultado"], resultado["motivo"]) == ("conflicto", "salto_de_estado")
    assert resultado["servicio"]["estado"] == origen.value  # la app corrige el suyo
    assert estado_de(servicio) == origen
    assert guardado(evento).resultado == ResultadoEvento.CONFLICTO
    assert alertas_de(evento).count() == 1
    assert not LineaCobro.objects.exists()


@pytest.mark.parametrize("destino", ["cancelado", "asignado", "pendiente_asignar"])
def test_un_destino_que_no_es_de_la_app_es_conflicto_y_el_servicio_no_cambia(
    sesion, ana, crear_servicio, destino
):
    # El conductor no cancela: la app solo tiene En camino, Recogido, Entregado y Novedad.
    servicio = crear_servicio(E.EN_CAMINO)
    evento = evento_json(servicio, destino, motivo="El cliente no estaba")

    (resultado,) = enviar(sesion, evento)

    assert (resultado["resultado"], resultado["motivo"]) == ("conflicto", "destino_no_permitido")
    servicio.refresh_from_db()
    assert (servicio.estado, servicio.conductor) == (E.EN_CAMINO, ana)
    fila = guardado(evento)
    assert (fila.resultado, fila.destino, fila.motivo) == (
        ResultadoEvento.CONFLICTO,
        destino,
        "El cliente no estaba",
    )
    assert alertas_de(evento).count() == 1


@pytest.mark.parametrize("motivo", [None, "", "   "])
def test_una_novedad_sin_motivo_es_conflicto(sesion, crear_servicio, motivo):
    servicio = crear_servicio(E.EN_CAMINO)
    evento = evento_json(servicio, E.NOVEDAD, motivo=motivo)

    (resultado,) = enviar(sesion, evento)

    assert (resultado["resultado"], resultado["motivo"]) == ("conflicto", "novedad_sin_motivo")
    assert estado_de(servicio) == E.EN_CAMINO
    assert alertas_de(evento).count() == 1


def test_un_evento_sobre_un_servicio_con_novedad_abierta_es_conflicto(sesion, crear_servicio):
    servicio = crear_servicio(E.NOVEDAD, previo=E.EN_CAMINO)
    evento = evento_json(servicio, E.RECOGIDO)

    (resultado,) = enviar(sesion, evento)

    assert (resultado["resultado"], resultado["motivo"]) == ("conflicto", "novedad_abierta")
    assert resultado["servicio"] == en_su_ronda(servicio, "novedad", previo="en_camino")


def test_recogido_sin_placa_ni_vin_es_conflicto(sesion, crear_servicio, nuevo_vehiculo):
    servicio = crear_servicio(E.EN_CAMINO, vehiculo=nuevo_vehiculo(placa="", vin=""))
    evento = evento_json(servicio, E.RECOGIDO)

    (resultado,) = enviar(sesion, evento)

    assert (resultado["resultado"], resultado["motivo"]) == (
        "conflicto",
        "identificacion_incompleta",
    )
    assert estado_de(servicio) == E.EN_CAMINO
    assert guardado(evento).motivo_conflicto == "identificacion_incompleta"


# --- Orden: la secuencia del dispositivo, no su reloj ni el orden de llegada ---------------------


def test_un_lote_desordenado_se_aplica_por_secuencia_y_no_por_la_hora_del_celular(
    sesion, crear_servicio
):
    servicio = crear_servicio(E.ASIGNADO)
    # Llegan al revés, y el reloj del celular dice que el segundo toque fue un año antes.
    entregado = evento_json(
        servicio, E.ENTREGADO, secuencia=30, hora_dispositivo="2026-11-20T13:30:00Z"
    )
    recogido = evento_json(
        servicio, E.RECOGIDO, secuencia=20, hora_dispositivo="2025-11-20T13:00:00Z"
    )
    en_camino = evento_json(
        servicio, E.EN_CAMINO, secuencia=10, hora_dispositivo="2026-11-20T13:10:00Z"
    )

    resultados = enviar(sesion, entregado, recogido, en_camino)

    # Los resultados vienen en el orden en que se enviaron.
    assert [r["id"] for r in resultados] == [entregado["id"], recogido["id"], en_camino["id"]]
    assert [r["resultado"] for r in resultados] == ["aplicado"] * 3
    assert estado_de(servicio) == E.ENTREGADO
    assert list(
        EventoEstado.objects.order_by("hora_sincronizacion").values_list("secuencia", flat=True)
    ) == [10, 20, 30]
    assert not Alerta.objects.exists()


def test_si_la_secuencia_7_llega_en_un_lote_anterior_a_la_6_no_se_pierde_ninguna(
    sesion, crear_servicio
):
    """Lotes que se cruzan: cada evento se evalúa contra el estado que encuentra. El que llegó
    antes de tiempo queda guardado como conflicto con alerta; el otro se aplica."""
    servicio = crear_servicio(E.ASIGNADO)
    sexto = evento_json(servicio, E.EN_CAMINO, secuencia=6)
    septimo = evento_json(servicio, E.RECOGIDO, secuencia=7)

    (resultado_7,) = enviar(sesion, septimo)
    (resultado_6,) = enviar(sesion, sexto)

    assert (resultado_7["resultado"], resultado_7["motivo"]) == ("conflicto", "salto_de_estado")
    assert resultado_6["resultado"] == "aplicado"
    assert estado_de(servicio) == E.EN_CAMINO
    assert EventoEstado.objects.count() == 2  # los dos toques quedaron en el historial
    assert alertas_de(septimo).count() == 1
    # Y el conflicto no se vuelve a evaluar aunque ahora encajaría.
    (repetido,) = enviar(sesion, septimo)
    assert (repetido["resultado"], repetido["duplicado"]) == ("conflicto", True)
    assert estado_de(servicio) == E.EN_CAMINO


def test_la_respuesta_trae_el_estado_del_servicio_al_terminar_el_lote(sesion, crear_servicio):
    servicio = crear_servicio(E.ASIGNADO)

    resultados = enviar(
        sesion,
        evento_json(servicio, E.EN_CAMINO, secuencia=1),
        evento_json(servicio, E.RECOGIDO, secuencia=2),
    )

    # Los dos resultados dicen lo mismo del servicio: cómo quedó, no cómo iba en cada paso.
    assert [r["servicio"] for r in resultados] == [
        en_su_ronda(servicio, "recogido", montado=True)
    ] * 2


# --- Capacidad: se revalida en el servidor -------------------------------------------------------


def test_recogido_que_excede_la_capacidad_se_aplica_con_la_marca_y_abre_alerta(
    sesion, crear_servicio
):
    montado = crear_servicio(E.RECOGIDO)  # la grúa de Ana, de un puesto, ya va llena
    servicio = crear_servicio(E.EN_CAMINO)
    evento = evento_json(servicio, E.RECOGIDO)

    (resultado,) = enviar(sesion, evento)

    # Ya pasó físicamente: se aplica, queda marcado y logística se entera.
    assert (resultado["resultado"], resultado["capacidad_excedida"]) == ("aplicado", True)
    assert resultado["motivo"] is None
    assert estado_de(servicio) == E.RECOGIDO
    fila = guardado(evento)
    assert (fila.resultado, fila.capacidad_excedida) == (ResultadoEvento.APLICADO, True)
    alerta = alertas_de(evento, TipoAlerta.CAPACIDAD_EXCEDIDA).get()
    assert "GRU001" in alerta.mensaje and "capacidad 1" in alerta.mensaje
    assert str(montado) in alerta.mensaje  # dice qué vehículo ya iba montado
    assert not alertas_de(evento).exists()  # no es un conflicto


def test_recogido_con_puesto_libre_no_queda_marcado_ni_alerta(
    sesion_beto, beto, crear_servicio
):
    crear_servicio(E.RECOGIDO, conductor=beto)  # grúa de dos puestos
    servicio = crear_servicio(E.EN_CAMINO, conductor=beto)
    evento = evento_json(servicio, E.RECOGIDO)

    (resultado,) = enviar(sesion_beto, evento)

    assert (resultado["resultado"], resultado["capacidad_excedida"]) == ("aplicado", False)
    assert guardado(evento).capacidad_excedida is False
    assert not Alerta.objects.exists()


def test_entregar_y_recoger_en_el_mismo_lote_no_excede_la_capacidad(sesion, crear_servicio):
    primero = crear_servicio(E.RECOGIDO)
    segundo = crear_servicio(E.EN_CAMINO)

    # Llegan al revés: por secuencia, primero se entrega el que iba montado.
    resultados = enviar(
        sesion,
        evento_json(segundo, E.RECOGIDO, secuencia=2),
        evento_json(primero, E.ENTREGADO, secuencia=1),
    )

    assert [(r["resultado"], r["capacidad_excedida"]) for r in resultados] == [
        ("aplicado", False)
    ] * 2
    assert not Alerta.objects.exists()


# --- Línea de cobro: en la misma transacción que el Entregado ------------------------------------


def test_entregado_desde_la_app_crea_la_linea_de_cobro(sesion, cliente, crear_servicio):
    Tarifa.objects.create(
        cliente=cliente, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal(180000)
    )
    servicio = crear_servicio(E.RECOGIDO)

    (resultado,) = enviar(sesion, evento_json(servicio, E.ENTREGADO, nombre_quien="Recepción"))

    assert resultado["resultado"] == "aplicado"
    linea = LineaCobro.objects.get(servicio=servicio)
    assert (linea.estado, linea.valor, linea.pagador) == ("por_facturar", Decimal(180000), cliente)


def test_si_la_linea_de_cobro_falla_el_entregado_no_se_guarda_y_la_app_lo_reintenta(
    sesion, monkeypatch, crear_servicio
):
    servicio = crear_servicio(E.RECOGIDO)
    evento = evento_json(servicio, E.ENTREGADO)

    with monkeypatch.context() as parche:

        def tarifa_que_falla(*args, **kwargs):
            raise RuntimeError("No se pudo leer la tarifa")

        parche.setattr(cobro, "tarifa_propuesta", tarifa_que_falla)
        (fallido,) = enviar(sesion, evento)

    # Todo o nada: ni evento, ni estado, ni línea. La respuesta no es un conflicto.
    assert (fallido["resultado"], fallido["motivo"]) == ("reintentar", "error_del_servidor")
    assert fallido["servicio"] == en_su_ronda(servicio, "recogido", montado=True)
    assert estado_de(servicio) == E.RECOGIDO
    assert not EventoEstado.objects.exists()
    assert not LineaCobro.objects.exists()
    assert not Alerta.objects.exists()

    # El celular lo conserva y lo reenvía: ahora sí entra, con su línea.
    (reintento,) = enviar(sesion, evento)
    assert (reintento["resultado"], reintento["duplicado"]) == ("aplicado", False)
    assert estado_de(servicio) == E.ENTREGADO
    assert LineaCobro.objects.filter(servicio=servicio).count() == 1


def test_un_conflicto_al_entregar_no_crea_linea_de_cobro(sesion, crear_servicio):
    servicio = crear_servicio(E.EN_CAMINO)

    (resultado,) = enviar(sesion, evento_json(servicio, E.ENTREGADO))

    assert resultado["resultado"] == "conflicto"
    assert not LineaCobro.objects.exists()


# --- Un evento malo no tumba los demás -----------------------------------------------------------


def test_un_conflicto_en_un_lote_no_detiene_los_demas(sesion, crear_servicio, usuario):
    cancelado = crear_servicio(E.ASIGNADO)
    operaciones.cambiar_estado(cancelado, E.CANCELADO, actor=usuario, motivo="Desistió")
    vigente = crear_servicio(E.ASIGNADO)

    resultados = enviar(
        sesion,
        evento_json(cancelado, E.EN_CAMINO, secuencia=1),
        evento_json(vigente, E.EN_CAMINO, secuencia=2),
    )

    assert [r["resultado"] for r in resultados] == ["conflicto", "aplicado"]
    assert (estado_de(cancelado), estado_de(vigente)) == (E.CANCELADO, E.EN_CAMINO)


def test_un_evento_que_falla_no_tumba_los_de_otros_servicios_y_frena_los_del_suyo(
    sesion, monkeypatch, crear_servicio
):
    con_falla = crear_servicio(E.EN_CAMINO)
    independiente = crear_servicio(E.ASIGNADO)
    recogido = evento_json(con_falla, E.RECOGIDO, secuencia=1)
    en_camino = evento_json(independiente, E.EN_CAMINO, secuencia=2)
    entregado = evento_json(con_falla, E.ENTREGADO, secuencia=3)

    with monkeypatch.context() as parche:

        def base_caida(servicio):
            raise RuntimeError("La base no respondió")

        parche.setattr(operaciones, "_verificar_capacidad", base_caida)
        resultados = enviar(sesion, recogido, en_camino, entregado)

    assert [(r["resultado"], r["motivo"]) for r in resultados] == [
        ("reintentar", "error_del_servidor"),
        ("aplicado", None),
        # No se evalúa contra un estado al que le falta el evento anterior (sería un conflicto
        # falso y definitivo): espera a que el celular reenvíe los dos.
        ("reintentar", "espera_evento_anterior"),
    ]
    assert (estado_de(con_falla), estado_de(independiente)) == (E.EN_CAMINO, E.EN_CAMINO)
    assert list(EventoEstado.objects.values_list("pk", flat=True)) == [
        uuid.UUID(en_camino["id"])
    ]
    assert not Alerta.objects.exists()

    # Reenvío del lote entero: entran los dos que faltaban, en orden, y el otro es duplicado.
    resultados = enviar(sesion, recogido, en_camino, entregado)
    assert [(r["resultado"], r["duplicado"]) for r in resultados] == [
        ("aplicado", False),
        ("aplicado", True),
        ("aplicado", False),
    ]
    assert estado_de(con_falla) == E.ENTREGADO


@pytest.mark.parametrize(
    ("cambio", "campo"),
    [
        ({"id": "no-es-un-uuid"}, "id"),
        ({"id": None}, "id"),
        ({"servicio_id": "abc"}, "servicio_id"),
        ({"destino": "volando"}, "destino"),
        ({"secuencia": None}, "secuencia"),
        ({"secuencia": "siete"}, "secuencia"),
    ],
)
def test_un_evento_ilegible_se_rechaza_solo_y_los_demas_del_lote_se_aplican(
    sesion, ana, crear_servicio, cambio, campo
):
    servicio = crear_servicio(E.ASIGNADO)
    malo = {**evento_json(servicio, E.EN_CAMINO, secuencia=1), **cambio}
    bueno = evento_json(servicio, E.EN_CAMINO, secuencia=2)

    resultados = enviar(sesion, malo, bueno)

    rechazado, aplicado = resultados
    assert (rechazado["resultado"], rechazado["motivo"]) == ("rechazado", "datos_invalidos")
    assert campo in rechazado["campos"]
    assert rechazado["servicio"] is None
    assert rechazado["id"] == (malo["id"] if isinstance(malo["id"], str) else None)
    assert aplicado["resultado"] == "aplicado"
    assert estado_de(servicio) == E.EN_CAMINO
    assert EventoEstado.objects.count() == 1
    # No se guardó, pero logística se entera: alerta sobre el conductor con lo que llegó.
    alerta = Alerta.objects.get()
    assert (alerta.tipo, alerta.registro) == (TipoAlerta.EVENTO_RECHAZADO, ana)
    assert "datos que no se pueden leer" in alerta.mensaje


def test_si_no_se_puede_avisar_de_un_evento_ilegible_el_celular_lo_conserva(
    sesion, monkeypatch, crear_servicio
):
    def sin_alertas(**datos):
        raise RuntimeError("No se pudo abrir la alerta")

    monkeypatch.setattr(operaciones, "registrar_evento_rechazado", sin_alertas)
    servicio = crear_servicio(E.ASIGNADO)
    malo = {**evento_json(servicio, E.EN_CAMINO, secuencia=1), "destino": "volando"}

    ilegible, aplicado = enviar(sesion, malo, evento_json(servicio, E.EN_CAMINO, secuencia=2))

    # Rechazarlo sin dejar rastro sería perderlo: mejor que lo reenvíe.
    assert (ilegible["resultado"], ilegible["motivo"]) == ("reintentar", "error_del_servidor")
    assert "campos" not in ilegible
    assert aplicado["resultado"] == "aplicado"


@pytest.mark.parametrize("basura", ["texto", 7, None, ["lista"]])
def test_un_elemento_del_lote_que_no_es_un_objeto_se_rechaza_solo(
    sesion, crear_servicio, basura
):
    servicio = crear_servicio(E.ASIGNADO)

    rechazado, aplicado = enviar(sesion, basura, evento_json(servicio, E.EN_CAMINO))

    assert (rechazado["id"], rechazado["resultado"]) == (None, "rechazado")
    assert rechazado["motivo"] == "datos_invalidos"
    assert aplicado["resultado"] == "aplicado"


def test_un_evento_sobre_un_servicio_que_no_existe_se_rechaza_y_avisa(sesion, ana, crear_servicio):
    servicio = crear_servicio(E.ASIGNADO)
    fantasma = evento_json(999_999_999, E.EN_CAMINO, secuencia=1)

    rechazado, aplicado = enviar(sesion, fantasma, evento_json(servicio, E.EN_CAMINO, secuencia=2))

    assert (rechazado["resultado"], rechazado["motivo"]) == ("rechazado", "servicio_desconocido")
    assert rechazado["servicio"] is None
    assert aplicado["resultado"] == "aplicado"
    assert not EventoEstado.objects.filter(pk=fantasma["id"]).exists()
    alerta = Alerta.objects.get()
    assert (alerta.tipo, alerta.registro) == (TipoAlerta.EVENTO_RECHAZADO, ana)
    assert "El servicio no existe." in alerta.mensaje


@pytest.mark.parametrize(
    "cambio",
    [
        {"hora_dispositivo": "ayer por la tarde"},
        {"hora_dispositivo": None},
        {"hora_dispositivo": 12345},
        {"latitud": "norte", "longitud": "oeste"},
        {"latitud": "nan", "longitud": "inf"},
        {"nombre_quien": {"nombre": "Juan"}},
        {"nombre_quien": "Juan\x00"},  # un carácter nulo, que PostgreSQL no guarda en un texto
    ],
)
def test_un_dato_secundario_ilegible_no_impide_guardar_lo_que_hizo_el_conductor(
    sesion, crear_servicio, cambio
):
    servicio = crear_servicio(E.EN_CAMINO)
    evento = {**evento_json(servicio, E.RECOGIDO), **cambio}

    (resultado,) = enviar(sesion, evento)

    assert resultado["resultado"] == "aplicado"
    assert estado_de(servicio) == E.RECOGIDO
    fila = guardado(evento)
    if "hora_dispositivo" in cambio:
        assert fila.hora_dispositivo is None
        assert fila.hora_sincronizacion is not None
    if "latitud" in cambio:
        assert (fila.latitud, fila.longitud) == (None, None)
    if "nombre_quien" in cambio:
        assert fila.nombre_quien == ""


def test_una_hora_sin_zona_se_toma_como_hora_de_colombia(sesion, crear_servicio):
    servicio = crear_servicio(E.ASIGNADO)
    evento = evento_json(servicio, E.EN_CAMINO, hora_dispositivo="2026-11-20T08:42:07")

    enviar(sesion, evento)

    assert guardado(evento).hora_dispositivo == datetime(2026, 11, 20, 13, 42, 7, tzinfo=UTC)


# --- Forma del lote y acceso ---------------------------------------------------------------------


def test_un_lote_vacio_responde_sin_resultados(sesion):
    assert enviar(sesion) == []


@pytest.mark.parametrize("cuerpo", [{}, {"eventos": None}, {"eventos": "uno"}, {"eventos": {}}])
def test_un_cuerpo_sin_la_lista_de_eventos_responde_400(sesion, cuerpo):
    respuesta = sesion.post(URL_EVENTOS, cuerpo, format="json")

    assert respuesta.status_code == 400
    assert respuesta.json() == {
        "version": 1,
        "error": "datos_invalidos",
        "detalle": "Revise los datos enviados.",
        "campos": {"eventos": ["Envíe la lista de eventos."]},
    }


def test_un_cuerpo_que_es_una_lista_y_no_un_objeto_responde_400(sesion):
    respuesta = sesion.post(URL_EVENTOS, [], format="json")
    assert (respuesta.status_code, respuesta.json()["error"]) == (400, "datos_invalidos")


def test_un_lote_de_mas_de_100_eventos_responde_400_y_no_aplica_ninguno(sesion, crear_servicio):
    servicio = crear_servicio(E.ASIGNADO)
    lote = [evento_json(servicio, E.EN_CAMINO, secuencia=n) for n in range(101)]

    respuesta = sesion.post(URL_EVENTOS, {"eventos": lote}, format="json")

    assert respuesta.status_code == 400
    assert respuesta.json()["campos"] == {"eventos": ["Máximo 100 eventos por lote."]}
    assert not EventoEstado.objects.exists()
    assert estado_de(servicio) == E.ASIGNADO


def test_un_lote_de_100_eventos_se_recibe(sesion, crear_servicio):
    servicio = crear_servicio(E.ASIGNADO)
    lote = [evento_json(servicio, E.EN_CAMINO, secuencia=n) for n in range(100)]

    resultados = enviar(sesion, *lote)

    assert [r["resultado"] for r in resultados] == ["aplicado"] + ["conflicto"] * 99
    assert EventoEstado.objects.count() == 100


def test_sin_token_no_se_reciben_eventos(api, crear_servicio):
    servicio = crear_servicio(E.ASIGNADO)

    respuesta = api.post(
        URL_EVENTOS, {"eventos": [evento_json(servicio, E.EN_CAMINO)]}, format="json"
    )

    assert (respuesta.status_code, respuesta.json()["error"]) == (401, "no_autenticado")
    assert not EventoEstado.objects.exists()


def test_un_conductor_inactivo_no_envia_eventos_y_los_conserva_el_celular(
    sesion, ana, crear_servicio
):
    servicio = crear_servicio(E.ASIGNADO)
    ana.activo = False
    ana.save()

    respuesta = sesion.post(
        URL_EVENTOS, {"eventos": [evento_json(servicio, E.EN_CAMINO)]}, format="json"
    )

    assert (respuesta.status_code, respuesta.json()["error"]) == (401, "conductor_no_habilitado")
    assert not EventoEstado.objects.exists()


def test_solo_se_envian_eventos_con_post(sesion):
    respuesta = sesion.get(URL_EVENTOS)
    assert (respuesta.status_code, respuesta.json()["error"]) == (405, "metodo_no_permitido")


# --- Nunca valores de cobro ----------------------------------------------------------------------


def test_las_respuestas_de_eventos_no_contienen_ningun_valor_de_cobro(
    sesion, cliente, crear_servicio, usuario
):
    pagador = Cliente.objects.create(
        nombre="Aseguradora Pagadora Única", tipo=TipoCliente.ASEGURADORA
    )
    solicitud = crear_solicitud(cliente, pagador=pagador)
    Tarifa.objects.create(
        cliente=pagador, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal("876543.21")
    )
    por_entregar = crear_servicio(E.RECOGIDO, solicitud_de=solicitud)
    cancelado = crear_servicio(E.ASIGNADO, solicitud_de=solicitud)
    operaciones.cambiar_estado(cancelado, E.CANCELADO, actor=usuario, motivo="Desistió")
    lote = [
        evento_json(por_entregar, E.ENTREGADO, secuencia=1),  # aplicado: nace la línea
        evento_json(cancelado, E.EN_CAMINO, secuencia=2),  # conflicto
        evento_json(999_999_999, E.EN_CAMINO, secuencia=3),  # rechazado
        {"id": "x"},  # ilegible
    ]

    for _ in range(2):  # la primera vez y el reenvío (duplicados)
        respuesta = sesion.post(URL_EVENTOS, {"eventos": lote}, format="json")
        assert respuesta.status_code == 200
        claves = set(_claves(respuesta.json()))
        assert not {c for c in claves if any(f in c.lower() for f in FRAGMENTOS_DE_COBRO)}
        texto = respuesta.content.decode()
        for prohibido in ("876543", "Aseguradora Pagadora", "por_facturar"):
            assert prohibido not in texto

    assert LineaCobro.objects.get(servicio=por_entregar).valor == Decimal("876543.21")
