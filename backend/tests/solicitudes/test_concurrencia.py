"""Peticiones simultáneas de verdad: dos hilos, dos conexiones a PostgreSQL, datos ya confirmados.

Estas pruebas son transaccionales (cada hilo ve lo que el otro confirma) y pytest-django las corre
después de las demás pruebas con base de datos. Sea cual sea el orden en que se crucen los hilos,
el resultado tiene que ser el mismo: un solo evento por id y un solo cambio de estado.
"""
import threading
import uuid

import pytest
from django.db import connection

from nucleo.capacidad import CapacidadExcedida
from nucleo.estados import Estado
from nucleo.sincronizacion import Resultado
from solicitudes import operaciones
from solicitudes.models import EventoEstado
from solicitudes.operaciones import aplicar_evento_del_conductor

pytestmark = pytest.mark.django_db(transaction=True)

E = Estado


def en_paralelo(*tareas):
    """Corre las tareas a la vez (arrancan juntas) y devuelve lo que devolvió o lanzó cada una."""
    barrera = threading.Barrier(len(tareas))
    salidas = [None] * len(tareas)

    def correr(posicion, tarea):
        try:
            barrera.wait(timeout=10)
            salidas[posicion] = tarea()
        # Cualquier error del hilo se devuelve para que la prueba lo revise en el hilo principal.
        except Exception as error:  # noqa: BLE001
            salidas[posicion] = error
        finally:
            connection.close()  # la conexión de este hilo

    hilos = [threading.Thread(target=correr, args=par) for par in enumerate(tareas)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)
    assert not any(hilo.is_alive() for hilo in hilos), "un hilo quedó bloqueado"
    return salidas


def test_el_mismo_evento_enviado_dos_veces_a_la_vez_se_aplica_una_sola_vez(
    crear_servicio, evento_app
):
    servicio = crear_servicio(E.ASIGNADO)
    datos = evento_app(servicio, E.EN_CAMINO)

    salidas = en_paralelo(
        lambda: aplicar_evento_del_conductor(**datos),
        lambda: aplicar_evento_del_conductor(**datos),
    )

    assert sorted(salidas) == sorted([Resultado.APLICADO, Resultado.DUPLICADO])
    assert EventoEstado.objects.count() == 1
    servicio.refresh_from_db()
    assert servicio.estado == E.EN_CAMINO


def test_el_mismo_id_a_la_vez_en_dos_servicios_choca_en_la_llave_y_aplica_uno_solo(
    monkeypatch, crear_servicio, evento_app
):
    # Sin la consulta previa, las dos peticiones llegan hasta el INSERT al mismo tiempo (cada una
    # con su servicio bloqueado): solo la llave primaria del evento las separa.
    monkeypatch.setattr(operaciones, "_ya_recibido", lambda evento_id: False)
    primero = crear_servicio(E.ASIGNADO)
    segundo = crear_servicio(E.ASIGNADO)
    id_repetido = uuid.uuid4()

    salidas = en_paralelo(
        lambda: aplicar_evento_del_conductor(**evento_app(primero, E.EN_CAMINO, id=id_repetido)),
        lambda: aplicar_evento_del_conductor(**evento_app(segundo, E.EN_CAMINO, id=id_repetido)),
    )

    assert sorted(salidas) == sorted([Resultado.APLICADO, Resultado.DUPLICADO])
    assert EventoEstado.objects.count() == 1
    estados = []
    for servicio in (primero, segundo):
        servicio.refresh_from_db()
        estados.append(servicio.estado)
    assert sorted(estados) == sorted([E.ASIGNADO, E.EN_CAMINO])  # solo uno cambió
    ganador = EventoEstado.objects.get(pk=id_repetido).servicio
    ganador.refresh_from_db()
    assert ganador.estado == E.EN_CAMINO


def test_dos_recogidas_a_la_vez_en_una_grua_de_un_puesto_desde_el_panel_dejan_pasar_una(
    crear_servicio, usuario
):
    primero = crear_servicio(E.EN_CAMINO)
    segundo = crear_servicio(E.EN_CAMINO)

    salidas = en_paralelo(
        lambda: operaciones.cambiar_estado(primero, E.RECOGIDO, actor=usuario),
        lambda: operaciones.cambiar_estado(segundo, E.RECOGIDO, actor=usuario),
    )

    errores = [s for s in salidas if isinstance(s, Exception)]
    assert len(errores) == 1 and isinstance(errores[0], CapacidadExcedida), salidas
    assert EventoEstado.objects.count() == 1
    estados = []
    for servicio in (primero, segundo):
        servicio.refresh_from_db()
        estados.append(servicio.estado)
    assert sorted(estados) == sorted([E.RECOGIDO, E.EN_CAMINO])


def test_dos_recogidas_a_la_vez_desde_la_app_se_aplican_y_solo_una_queda_marcada(
    crear_servicio, evento_app
):
    primero = crear_servicio(E.EN_CAMINO)
    segundo = crear_servicio(E.EN_CAMINO)

    salidas = en_paralelo(
        lambda: aplicar_evento_del_conductor(**evento_app(primero, E.RECOGIDO, secuencia=1)),
        lambda: aplicar_evento_del_conductor(**evento_app(segundo, E.RECOGIDO, secuencia=2)),
    )

    assert salidas == [Resultado.APLICADO, Resultado.APLICADO]
    marcas = sorted(EventoEstado.objects.values_list("capacidad_excedida", flat=True))
    assert marcas == [False, True]
