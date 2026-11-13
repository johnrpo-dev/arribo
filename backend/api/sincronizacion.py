"""Envío de eventos de la app (`POST /api/v1/eventos/`, ver `docs/api-conductor.md`).

Aquí solo se lee lo que manda el celular y se arma la respuesta. Aplicar los eventos (orden por
secuencia, idempotencia, conflictos, capacidad, línea de cobro, alertas) es de
`solicitudes.operaciones.sincronizar_lote_del_conductor`, con las reglas de `nucleo/`.

Lo que el conductor hizo no se pierde por un dato raro del celular: de un evento solo son
indispensables su id, el servicio, el destino y la secuencia. La hora del celular, la ubicación y
los textos que no se puedan leer se guardan vacíos en vez de rechazar el evento.
"""
import math
from datetime import UTC

from rest_framework import serializers

from nucleo.estados import Estado, a_bordo
from nucleo.sincronizacion import DETALLE, Motivo, Resultado
from solicitudes import operaciones
from solicitudes.models import VALORES_EN_RONDA, Servicio

MAXIMO_DE_EVENTOS_POR_LOTE = 100
ENTERO_MAXIMO = 2**63 - 1  # lo que cabe en la columna de la secuencia


class _Tolerante:
    """Campo que no es indispensable: si no se puede leer, queda vacío y el evento sigue."""

    def run_validation(self, data=serializers.empty):
        try:
            return super().run_validation(data)
        except serializers.ValidationError:
            return None


class _Hora(_Tolerante, serializers.DateTimeField):
    def run_validation(self, data=serializers.empty):
        valor = super().run_validation(data)
        try:
            return valor and valor.astimezone(UTC)
        except (OverflowError, ValueError):  # una fecha en el borde del calendario
            return None


class _Numero(_Tolerante, serializers.FloatField):
    def run_validation(self, data=serializers.empty):
        valor = super().run_validation(data)
        return valor if valor is not None and math.isfinite(valor) else None


class _Texto(_Tolerante, serializers.CharField):
    pass


class EventoSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    servicio_id = serializers.IntegerField(min_value=1, max_value=ENTERO_MAXIMO)
    destino = serializers.ChoiceField(choices=[estado.value for estado in Estado])
    secuencia = serializers.IntegerField(min_value=-ENTERO_MAXIMO, max_value=ENTERO_MAXIMO)
    hora_dispositivo = _Hora(required=False, allow_null=True, default=None)
    motivo = _Texto(required=False, allow_null=True, allow_blank=True, default=None)
    nombre_quien = _Texto(required=False, allow_null=True, allow_blank=True, default=None)
    latitud = _Numero(required=False, allow_null=True, default=None)
    longitud = _Numero(required=False, allow_null=True, default=None)


def leer_lote(cuerpo) -> list:
    """La lista `eventos` del cuerpo, o `ValidationError` (400) si el cuerpo no tiene esa forma.
    Cada evento se valida después, por separado: uno malo no tumba el lote."""
    eventos = cuerpo.get("eventos") if isinstance(cuerpo, dict) else None
    if not isinstance(eventos, list):
        raise serializers.ValidationError({"eventos": ["Envíe la lista de eventos."]})
    if len(eventos) > MAXIMO_DE_EVENTOS_POR_LOTE:
        raise serializers.ValidationError(
            {"eventos": [f"Máximo {MAXIMO_DE_EVENTOS_POR_LOTE} eventos por lote."]}
        )
    return eventos


def sincronizar(conductor, eventos: list) -> list[dict]:
    """Un resultado por evento, en el mismo orden en que llegaron."""
    resultados: list[dict | None] = [None] * len(eventos)
    validos, posiciones = [], []
    for posicion, crudo in enumerate(eventos):
        lectura = EventoSerializer(data=crudo)
        if lectura.is_valid():
            validos.append({**_para_aplicar(lectura.validated_data), "conductor": conductor})
            posiciones.append(posicion)
        else:
            resultados[posicion] = _ilegible(conductor, crudo, lectura.errors)

    aplicaciones = operaciones.sincronizar_lote_del_conductor(validos)
    servicios = _servicios_ahora(conductor, {a.servicio_id for a in aplicaciones})
    for posicion, aplicacion in zip(posiciones, aplicaciones, strict=True):
        resultados[posicion] = _resultado(aplicacion, servicios.get(aplicacion.servicio_id))
    return resultados


def _para_aplicar(datos) -> dict:
    datos = dict(datos)
    datos["servicio"] = datos.pop("servicio_id")
    return datos


def _ilegible(conductor, crudo, errores) -> dict:
    """Un evento sin id, servicio, destino o secuencia legibles no se puede guardar: se rechaza,
    queda en el registro del servidor y abre una alerta a logística con lo que llegó."""
    operaciones.registrar_evento_rechazado(
        conductor=conductor, motivo=Motivo.DATOS_INVALIDOS, contenido=crudo
    )
    identificador = crudo.get("id") if isinstance(crudo, dict) else None
    return {
        "id": identificador if isinstance(identificador, str) else None,
        "resultado": Resultado.RECHAZADO.value,
        "duplicado": False,
        "motivo": Motivo.DATOS_INVALIDOS.value,
        "detalle": DETALLE[Motivo.DATOS_INVALIDOS],
        "campos": errores if isinstance(crudo, dict) else {"evento": ["Debe ser un objeto."]},
        "capacidad_excedida": False,
        "servicio": None,
    }


def _resultado(aplicacion, servicio) -> dict:
    return {
        "id": aplicacion.id,
        "resultado": aplicacion.resultado.value,
        "duplicado": aplicacion.duplicado,
        "motivo": aplicacion.motivo.value if aplicacion.motivo else None,
        "detalle": DETALLE[aplicacion.motivo] if aplicacion.motivo else None,
        "capacidad_excedida": aplicacion.capacidad_excedida,
        "servicio": servicio,
    }


def _servicios_ahora(conductor, ids) -> dict[str, dict]:
    """El estado de cada servicio al terminar el lote (una sola consulta), para que la app corrija
    el suyo. De un servicio que ya no es del conductor no se dice el estado: solo que salió de su
    ronda."""
    return {
        str(servicio.pk): _servicio_para_la_app(servicio, conductor)
        for servicio in Servicio.objects.filter(pk__in=ids).only(
            "estado", "estado_previo", "conductor"
        )
    }


def _servicio_para_la_app(servicio, conductor) -> dict:
    suyo = servicio.conductor_id == conductor.pk
    return {
        "id": servicio.pk,
        "estado": servicio.estado if suyo else None,
        "estado_previo": (servicio.estado_previo or None) if suyo else None,
        "a_bordo": suyo and a_bordo(servicio.como_nucleo()),
        "en_su_ronda": suyo and servicio.estado in VALORES_EN_RONDA,
    }
