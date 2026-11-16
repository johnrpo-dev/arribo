"""Las reglas que la app del conductor copia cumplen los casos de `docs/casos-reglas.json`.

La app repite en Dart la máquina de estados, la capacidad, la identificación del vehículo (también
la placa o el VIN digitados al recoger) y los límites de las fotos. Ese archivo es el contrato entre
las dos copias: lo recorren estas pruebas y `conductor/test/casos_compartidos_test.dart`. Si una
regla cambia aquí, estas pruebas fallan hasta que el archivo cambie; y con el archivo cambiado falla
la prueba de la app hasta que cambie su copia.
"""
import json
from pathlib import Path

import pytest

from nucleo.capacidad import CapacidadExcedida, verificar_recogida
from nucleo.estados import (
    Estado,
    Servicio,
    TransicionInvalida,
    a_bordo,
    puede_transicionar,
    transicionar,
)
from nucleo.evidencia import (
    TAMANO_MAXIMO_FOTO,
    TIPOS_DESDE_LA_APP,
    acompana,
    es_jpeg,
    excede_el_tamano,
)
from nucleo.identificacion import (
    LARGO_MAXIMO_PLACA,
    IdentificacionIncompleta,
    PlacaInvalida,
    VinInvalido,
    completar_identificacion,
    identificacion_exigida,
    normalizar_placa,
    normalizar_vin,
    validar_identificacion,
    validar_identificacion_al_recoger,
    validar_placa,
    validar_vin,
)
from nucleo.sincronizacion import DESTINOS_DESDE_LA_APP
from nucleo.trayecto import PASOS_QUE_ESPERAN_LA_IDA, regreso_bloqueado

ARCHIVO = Path(__file__).resolve().parents[3] / "docs" / "casos-reglas.json"
CASOS = json.loads(ARCHIVO.read_text(encoding="utf-8"))
ESTADOS = CASOS["estados"]
IDENTIFICACION = CASOS["identificacion"]
EVIDENCIA = CASOS["evidencia"]
REGRESO = CASOS["regreso"]


def _servicio(caso) -> Servicio:
    previo = caso.get("estado_previo")
    return Servicio(Estado(caso["estado"]), Estado(previo) if previo else None)


def _nombre(caso) -> str:
    return caso.get("nombre") or json.dumps(caso, ensure_ascii=False)


# ---------- estados ----------


def test_el_archivo_nombra_todos_los_estados_y_los_destinos_de_la_app():
    assert set(ESTADOS["todos"]) == {estado.value for estado in Estado}
    assert set(ESTADOS["destinos_desde_la_app"]) == {d.value for d in DESTINOS_DESDE_LA_APP}


def test_el_archivo_trae_cada_par_de_estado_y_destino_una_sola_vez():
    pares = [(caso["estado"], caso["destino"]) for caso in ESTADOS["transiciones"]]
    esperados = {(estado.value, destino.value) for estado in Estado for destino in Estado}
    assert len(pares) == len(set(pares))
    assert set(pares) == esperados


@pytest.mark.parametrize(
    "caso", ESTADOS["transiciones"], ids=lambda c: f"{c['estado']}->{c['destino']}"
)
def test_transicion_permitida_o_prohibida_como_dice_el_archivo(caso):
    servicio = Servicio(Estado(caso["estado"]))
    destino = Estado(caso["destino"])
    permitida = puede_transicionar(servicio, destino)
    assert permitida == caso["permitida"]
    assert (permitida and destino in DESTINOS_DESDE_LA_APP) == caso["desde_la_app"]
    if caso["desde_la_app"]:
        queda = transicionar(servicio, destino, motivo="motivo")
        assert queda.estado.value == caso["queda"]["estado"]
        previo = queda.estado_previo.value if queda.estado_previo else None
        assert previo == caso["queda"]["estado_previo"]
    else:
        assert "queda" not in caso
    if not permitida:
        with pytest.raises(TransicionInvalida):
            transicionar(servicio, destino, motivo="motivo")


@pytest.mark.parametrize(
    "caso", ESTADOS["a_bordo"], ids=lambda c: f"{c['estado']}/{c['estado_previo']}"
)
def test_a_bordo_como_dice_el_archivo(caso):
    assert a_bordo(_servicio(caso)) == caso["a_bordo"]


# ---------- capacidad ----------


@pytest.mark.parametrize("caso", CASOS["capacidad"], ids=_nombre)
def test_capacidad_bloquea_y_dice_que_falta_entregar_como_dice_el_archivo(caso):
    montados = [otro["id"] for otro in caso["otros"] if a_bordo(_servicio(otro))]
    if caso["bloquea"]:
        with pytest.raises(CapacidadExcedida) as error:
            verificar_recogida(caso["capacidad"], montados)
        assert error.value.pendientes_de_entregar == caso["faltan_por_entregar"]
    else:
        verificar_recogida(caso["capacidad"], montados)
        assert caso["faltan_por_entregar"] == []


@pytest.mark.parametrize("capacidad", CASOS["capacidad_invalida"])
def test_capacidad_invalida_como_dice_el_archivo(capacidad):
    with pytest.raises(ValueError):
        verificar_recogida(capacidad, [])


# ---------- identificación ----------


@pytest.mark.parametrize("caso", IDENTIFICACION["placas"], ids=_nombre)
def test_placa_normalizada_como_dice_el_archivo(caso):
    assert normalizar_placa(caso["texto"]) == caso["normalizada"]


@pytest.mark.parametrize("caso", IDENTIFICACION["vin"], ids=_nombre)
def test_vin_normalizado_y_valido_como_dice_el_archivo(caso):
    vin = normalizar_vin(caso["texto"])
    assert vin == caso["normalizado"]
    if caso["valido"]:
        validar_vin(vin)
    else:
        with pytest.raises(VinInvalido):
            validar_vin(vin)


@pytest.mark.parametrize("caso", IDENTIFICACION["vehiculo"], ids=_nombre)
def test_identificacion_del_vehiculo_completa_o_no_como_dice_el_archivo(caso):
    if caso["completa"]:
        validar_identificacion(caso["placa"], caso["vin"], caso["tipo"])
    else:
        with pytest.raises(IdentificacionIncompleta):
            validar_identificacion(caso["placa"], caso["vin"], caso["tipo"])


@pytest.mark.parametrize("caso", IDENTIFICACION["exigida"], ids=_nombre)
def test_momento_en_que_se_exige_la_identificacion_como_dice_el_archivo(caso):
    assert identificacion_exigida(caso["configurado"], caso["momento"]) == caso["exigida"]


def test_largo_maximo_de_la_placa_como_dice_el_archivo():
    assert LARGO_MAXIMO_PLACA == IDENTIFICACION["largo_maximo_placa"]


@pytest.mark.parametrize("caso", IDENTIFICACION["placa_valida"], ids=_nombre)
def test_placa_valida_como_dice_el_archivo(caso):
    if caso["valida"]:
        validar_placa(caso["placa"])
    else:
        with pytest.raises(PlacaInvalida):
            validar_placa(caso["placa"])


@pytest.mark.parametrize("caso", IDENTIFICACION["al_recoger"], ids=_nombre)
def test_identificacion_al_recoger_con_lo_digitado_como_dice_el_archivo(caso):
    argumentos = (
        caso["vehiculo"]["placa"],
        caso["vehiculo"]["vin"],
        caso["digitada"]["placa"],
        caso["digitada"]["vin"],
        caso["tipo"],
    )
    if caso["completa"]:
        validar_identificacion_al_recoger(*argumentos)
    else:
        with pytest.raises(IdentificacionIncompleta):
            validar_identificacion_al_recoger(*argumentos)


@pytest.mark.parametrize("caso", IDENTIFICACION["completar"], ids=_nombre)
def test_lo_digitado_al_recoger_completa_el_vehiculo_como_dice_el_archivo(caso):
    complemento = completar_identificacion(
        caso["vehiculo"]["placa"],
        caso["vehiculo"]["vin"],
        caso["digitada"]["placa"],
        caso["digitada"]["vin"],
    )
    assert {"placa": complemento.placa, "vin": complemento.vin} == caso["queda"]
    assert [campo.value for campo in complemento.nuevos] == caso["nuevos"]
    assert [
        {
            "campo": dato.campo.value,
            "digitado": dato.digitado,
            "revision": dato.revision.value,
            "existente": dato.existente,
        }
        for dato in complemento.por_revisar
    ] == caso["por_revisar"]


# ---------- fotos ----------


def test_tamano_maximo_y_tipos_de_foto_como_dice_el_archivo():
    assert TAMANO_MAXIMO_FOTO == EVIDENCIA["tamano_maximo_bytes"]
    assert sorted(TIPOS_DESDE_LA_APP) == EVIDENCIA["tipos_desde_la_app"]


@pytest.mark.parametrize("caso", EVIDENCIA["tamanos"], ids=_nombre)
def test_foto_excede_el_tamano_como_dice_el_archivo(caso):
    assert excede_el_tamano(caso["bytes"]) == caso["excede"]


@pytest.mark.parametrize("caso", EVIDENCIA["jpeg"], ids=_nombre)
def test_foto_es_jpeg_como_dice_el_archivo(caso):
    assert es_jpeg(bytes(caso["primeros_bytes"])) == caso["es_jpeg"]


@pytest.mark.parametrize("caso", EVIDENCIA["acompana"], ids=_nombre)
def test_tipo_de_foto_acompana_a_su_evento_como_dice_el_archivo(caso):
    assert acompana(caso["tipo"], Estado(caso["destino"])) == caso["acompana"]


# ---------- regreso que espera a su ida ----------


def test_el_archivo_cubre_cada_destino_de_la_app_con_y_sin_ida_entregada():
    vistos = {(c["es_regreso"], c["ida_entregada"], c["destino"]) for c in REGRESO["casos"]}
    esperados = {
        (regreso, ida, destino.value)
        for regreso in (False, True)
        for ida in (False, True)
        for destino in DESTINOS_DESDE_LA_APP
    }
    assert vistos == esperados
    assert PASOS_QUE_ESPERAN_LA_IDA < DESTINOS_DESDE_LA_APP


@pytest.mark.parametrize("caso", REGRESO["casos"], ids=_nombre)
def test_regreso_bloqueado_como_dice_el_archivo(caso):
    assert (
        regreso_bloqueado(caso["es_regreso"], caso["ida_entregada"], caso["destino"])
        is caso["bloqueado"]
    )
