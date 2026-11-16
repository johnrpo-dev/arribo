"""Lo que la app envía y recibe (`docs/api-conductor.md`).

El conductor nunca recibe valores de cobro: estos serializadores arman cada respuesta campo por
campo, sin `fields = "__all__"` ni modelos anidados completos, y no leen la solicitud más allá de su
tipo, direcciones, contactos y horas (nada de pagador, tarifa, líneas de cobro ni factura).

Fechas en UTC, ISO 8601 con Z ("2026-11-13T19:30:00Z"). Los textos opcionales vacíos van como null.
"""
from datetime import UTC

from rest_framework import serializers

from nucleo.estados import a_bordo
from nucleo.identificacion import TelefonoInvalido, normalizar_telefono
from nucleo.ingreso import PinInvalido, validar_pin
from nucleo.trayecto import hora_programada, puntos_del_servicio

from .models import LARGO_MAXIMO_TOKEN_PUSH


def fecha_utc(valor):
    """ISO 8601 en UTC con Z, como "2026-11-13T19:30:00Z"; None queda None."""
    if valor is None:
        return None
    return valor.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _texto(valor):
    return valor or None


# --- Ingreso -------------------------------------------------------------------------------------


class IngresoSerializer(serializers.Serializer):
    celular = serializers.CharField(max_length=30)
    pin = serializers.CharField(max_length=20, trim_whitespace=False)
    dispositivo_id = serializers.CharField(max_length=100)
    dispositivo_nombre = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )

    def validate_celular(self, valor):
        try:
            return normalizar_telefono(valor)
        except TelefonoInvalido as error:
            raise serializers.ValidationError(str(error)) from error

    def validate_pin(self, valor):
        # Un PIN con otro formato no puede ser el correcto: se responde sin contarlo como fallo.
        try:
            validar_pin(valor)
        except PinInvalido as error:
            raise serializers.ValidationError(str(error)) from error
        return valor


class TokenPushSerializer(serializers.Serializer):
    """PUT /push/: el token que Firebase le dio a la app en este celular."""

    token = serializers.CharField(max_length=LARGO_MAXIMO_TOKEN_PUSH)

    def validate_token(self, valor):
        if any(caracter.isspace() for caracter in valor):
            raise serializers.ValidationError("El token de push no lleva espacios.")
        return valor


def conductor_para_la_app(conductor) -> dict:
    return {"id": conductor.pk, "nombre": conductor.nombre, "celular": conductor.celular}


# --- Asignaciones --------------------------------------------------------------------------------


def configuracion_para_la_app(configuracion) -> dict:
    """Lo que la app necesita de la configuración para trabajar sin señal."""
    return {
        "minimo_fotos": configuracion.minimo_fotos,
        "momento_placa_vin": configuracion.momento_placa_vin,
    }


def _contacto(contacto):
    if contacto is None:
        return None
    return {"nombre": contacto.nombre, "telefono": contacto.telefono}


def _punto(direccion, ubicacion, contacto) -> dict:
    return {
        "direccion": _texto(direccion),
        "ubicacion": _texto(ubicacion),
        "contacto": _contacto(contacto),
    }


class ServicioDelConductorSerializer(serializers.BaseSerializer):
    """Un servicio asignado, como lo ve el conductor. Solo lectura.

    `origen` es donde se recoge el vehículo y `destino` donde se entrega: en un regreso ya vienen
    invertidos respecto de la solicitud, y `programada_para` es la fecha de regreso
    (`nucleo/trayecto.py`).
    """

    def to_representation(self, servicio):
        solicitud = servicio.solicitud
        vehiculo = servicio.vehiculo
        grua = servicio.grua
        es_regreso = servicio.regreso_de_id is not None
        origen, destino = puntos_del_servicio(
            es_regreso,
            _punto(solicitud.origen, solicitud.origen_ubicacion, solicitud.contacto_origen),
            _punto(solicitud.destino, solicitud.destino_ubicacion, solicitud.contacto_destino),
        )
        return {
            "id": servicio.pk,
            "solicitud_id": servicio.solicitud_id,
            "estado": servicio.estado,
            "estado_previo": _texto(servicio.estado_previo),
            "tipo": solicitud.tipo,
            "es_regreso": es_regreso,
            # Revisión 1.3: el regreso espera a que su ida esté entregada (nucleo.trayecto).
            "regreso_de": servicio.regreso_de_id,
            "espera_ida": servicio.espera_su_ida,
            "orden_ronda": servicio.orden_ronda,
            "vehiculo": {
                "placa": _texto(vehiculo.placa),
                "vin": _texto(vehiculo.vin),
                "marca": _texto(vehiculo.marca),
                "linea": _texto(vehiculo.linea),
                "color": _texto(vehiculo.color),
            },
            "origen": origen,
            "destino": destino,
            "referencia_externa": _texto(servicio.referencia_externa),
            "programada_para": fecha_utc(
                hora_programada(es_regreso, solicitud.programada_para, solicitud.fecha_regreso)
            ),
            "grua": None if grua is None else {
                "id": grua.pk,
                "placa": grua.placa,
                "capacidad": grua.capacidad,
            },
            "a_bordo": a_bordo(servicio.como_nucleo()),
        }
