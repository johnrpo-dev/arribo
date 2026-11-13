"""`PUT /api/v1/evidencias/<uuid>/`: fotos de evidencia contra PostgreSQL y el disco.

Idempotente por el id del celular, en disco por partes y con nombre del servidor, solo JPEG y con
tope de tamaño. La foto puede llegar antes que su evento y se enlaza cuando el evento llega.
"""
import hashlib
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from alertas.models import Alerta
from nucleo.estados import Estado
from nucleo.evidencia import TAMANO_MAXIMO_FOTO
from solicitudes import evidencias, operaciones
from solicitudes.models import EventoEstado, Evidencia

from .conftest import JPEG, enviar, evento_json, subir, url_evidencia
from .test_asignaciones import FRAGMENTOS_DE_COBRO, _claves

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("media_temporal")]

E = Estado
OTRO_JPEG = b"\xff\xd8\xff\xe1" + b"otra foto distinta " * 30 + b"\xff\xd9"
NO_ENCONTRADO = {
    "version": 1,
    "error": "no_encontrado",
    "detalle": "El servicio no existe o nunca estuvo asignado a usted.",
}


def archivos_en(media) -> list[str]:
    return sorted(
        str(ruta.relative_to(media)).replace("\\", "/")
        for ruta in media.rglob("*")
        if ruta.is_file()
    )


@pytest.fixture
def recogido(sesion, crear_servicio):
    """Un servicio de Ana ya Recogido desde la app: (servicio, id del evento de Recogido)."""
    servicio = crear_servicio(E.EN_CAMINO)
    evento = evento_json(servicio, E.RECOGIDO, nombre_quien="Portero")
    assert enviar(sesion, evento)[0]["resultado"] == "aplicado"
    return servicio, evento["id"]


# --- Guardar -------------------------------------------------------------------------------------


def test_la_foto_se_guarda_en_disco_enlazada_a_su_evento(sesion, ana, recogido, media_temporal):
    servicio, evento_id = recogido

    respuesta, evidencia_id = subir(sesion, servicio, evento_id)

    assert respuesta.status_code == 201
    assert respuesta.json() == {
        "version": 1,
        "id": str(evidencia_id),
        "resultado": "guardada",
        "enlazada": True,
    }
    evidencia = Evidencia.objects.get(pk=evidencia_id)
    assert (evidencia.servicio, evidencia.tipo, evidencia.subida_por) == (servicio, "recogida", ana)
    assert str(evidencia.evento_id) == str(evidencia.evento_esperado) == evento_id
    assert (evidencia.sha256, evidencia.tamano) == (hashlib.sha256(JPEG).hexdigest(), len(JPEG))
    assert evidencia.archivo.name == f"evidencias/{servicio.pk}/{evidencia_id}.jpg"
    assert (media_temporal / evidencia.archivo.name).read_bytes() == JPEG


@pytest.mark.parametrize(
    "nombre", ["../../../etc/passwd", "foto.php", "C:\\Windows\\win.ini", "sin_extension", "a.PNG"]
)
def test_el_nombre_del_archivo_lo_pone_el_servidor_nunca_el_celular(
    sesion, recogido, media_temporal, nombre
):
    servicio, evento_id = recogido

    respuesta, evidencia_id = subir(sesion, servicio, evento_id, nombre=nombre)

    assert respuesta.status_code == 201
    assert archivos_en(media_temporal) == [f"evidencias/{servicio.pk}/{evidencia_id}.jpg"]


def test_una_foto_pequena_tambien_va_a_disco_y_no_a_memoria(sesion, recogido, monkeypatch):
    """Django deja en memoria los archivos de menos de 2,5 MB; esta vista no: siempre llega un
    archivo temporal en disco, que al guardar se mueve."""
    servicio, evento_id = recogido
    recibidos = []
    guardar = evidencias.guardar_foto

    def espiar(**datos):
        recibidos.append(datos["archivo"])
        return guardar(**datos)

    monkeypatch.setattr(evidencias, "guardar_foto", espiar)

    respuesta, _ = subir(sesion, servicio, evento_id)

    assert respuesta.status_code == 201
    (archivo,) = recibidos
    assert type(archivo).__name__ == "TemporaryUploadedFile"
    assert archivo.temporary_file_path()


def test_la_foto_de_entrega_acompana_al_evento_de_entregado(sesion, recogido):
    servicio, _ = recogido
    entregado = evento_json(servicio, E.ENTREGADO, secuencia=2)
    enviar(sesion, entregado)

    # El servicio ya terminó y salió de la ronda: sus fotos se siguen recibiendo.
    respuesta, evidencia_id = subir(sesion, servicio, entregado["id"], tipo="entrega")

    assert (respuesta.status_code, respuesta.json()["enlazada"]) == (201, True)
    assert str(Evidencia.objects.get(pk=evidencia_id).evento_id) == entregado["id"]


# --- Reintento: la misma foto no se duplica ------------------------------------------------------


def test_subir_la_misma_foto_dos_veces_no_la_duplica(sesion, recogido, media_temporal):
    servicio, evento_id = recogido
    primera, evidencia_id = subir(sesion, servicio, evento_id)
    guardada = Evidencia.objects.values().get(pk=evidencia_id)

    # Se cortó la señal antes de la respuesta: el celular sube la foto completa otra vez.
    segunda, _ = subir(sesion, servicio, evento_id, evidencia_id=evidencia_id)

    assert (primera.status_code, segunda.status_code) == (201, 200)
    assert segunda.json() == {
        "version": 1,
        "id": str(evidencia_id),
        "resultado": "repetida",
        "enlazada": True,
    }
    assert Evidencia.objects.count() == 1
    assert Evidencia.objects.values().get(pk=evidencia_id) == guardada
    assert archivos_en(media_temporal) == [f"evidencias/{servicio.pk}/{evidencia_id}.jpg"]


def test_el_mismo_id_con_otro_contenido_es_un_error_y_no_reemplaza_la_guardada(
    sesion, recogido, media_temporal
):
    servicio, evento_id = recogido
    _, evidencia_id = subir(sesion, servicio, evento_id)

    respuesta, _ = subir(sesion, servicio, evento_id, evidencia_id=evidencia_id, contenido=OTRO_JPEG)

    assert respuesta.status_code == 409
    assert respuesta.json() == {
        "version": 1,
        "error": "evidencia_distinta",
        "detalle": "Ya hay una foto guardada con ese id y no es esta. La guardada no se reemplaza.",
    }
    evidencia = Evidencia.objects.get()
    assert evidencia.sha256 == hashlib.sha256(JPEG).hexdigest()
    assert archivos_en(media_temporal) == [f"evidencias/{servicio.pk}/{evidencia_id}.jpg"]
    assert (media_temporal / evidencia.archivo.name).read_bytes() == JPEG


@pytest.mark.parametrize("cambio", ["tipo", "evento", "servicio"])
def test_el_mismo_id_con_otros_datos_tambien_es_un_error(
    sesion, recogido, crear_servicio, cambio
):
    servicio, evento_id = recogido
    _, evidencia_id = subir(sesion, servicio, evento_id)
    otros = {
        "tipo": {"tipo": "entrega"},
        "evento": {},
        "servicio": {},
    }[cambio]
    destino = crear_servicio(E.ASIGNADO) if cambio == "servicio" else servicio
    otro_evento = uuid.uuid4() if cambio == "evento" else evento_id

    respuesta, _ = subir(sesion, destino, otro_evento, evidencia_id=evidencia_id, **otros)

    assert (respuesta.status_code, respuesta.json()["error"]) == (409, "evidencia_distinta")
    guardada = Evidencia.objects.get()
    assert (guardada.servicio, guardada.tipo, str(guardada.evento_id)) == (
        servicio,
        "recogida",
        evento_id,
    )


# --- La foto puede llegar antes que su evento ----------------------------------------------------


def test_la_foto_que_llega_antes_que_su_evento_se_guarda_y_se_enlaza_cuando_el_evento_llega(
    sesion, crear_servicio, media_temporal
):
    servicio = crear_servicio(E.EN_CAMINO)
    evento = evento_json(servicio, E.RECOGIDO)

    respuesta, evidencia_id = subir(sesion, servicio, evento["id"])  # el evento aún no llegó

    assert respuesta.status_code == 201
    assert respuesta.json()["enlazada"] is False
    evidencia = Evidencia.objects.get(pk=evidencia_id)
    assert evidencia.evento is None
    assert str(evidencia.evento_esperado) == evento["id"]
    assert (media_temporal / evidencia.archivo.name).exists()

    enviar(sesion, evento)

    evidencia.refresh_from_db()
    assert str(evidencia.evento_id) == evento["id"]
    # Y el reintento de la foto ya la ve enlazada.
    repetida, _ = subir(sesion, servicio, evento["id"], evidencia_id=evidencia_id)
    assert (repetida.status_code, repetida.json()["enlazada"]) == (200, True)


def test_las_fotos_en_espera_tambien_se_enlazan_a_un_evento_que_queda_en_conflicto(
    sesion, crear_servicio, usuario
):
    servicio = crear_servicio(E.EN_CAMINO)
    evento = evento_json(servicio, E.RECOGIDO)
    _, primera = subir(sesion, servicio, evento["id"])
    _, segunda = subir(sesion, servicio, evento["id"], contenido=OTRO_JPEG)
    operaciones.cambiar_estado(servicio, E.CANCELADO, actor=usuario, motivo="Desistió")

    (resultado,) = enviar(sesion, evento)

    # Lo que el conductor hizo queda completo en el historial: el evento y sus fotos.
    assert resultado["resultado"] == "conflicto"
    assert {str(e.evento_id) for e in Evidencia.objects.filter(pk__in=[primera, segunda])} == {
        evento["id"]
    }


def test_el_duplicado_de_un_evento_no_toca_las_fotos_ya_enlazadas(sesion, recogido):
    servicio, evento_id = recogido
    _, evidencia_id = subir(sesion, servicio, evento_id)
    evento = EventoEstado.objects.get(pk=evento_id)

    enviar(sesion, evento_json(servicio, E.RECOGIDO, id=evento_id, nombre_quien="Portero"))

    assert Evidencia.objects.get(pk=evidencia_id).evento == evento


@pytest.mark.parametrize("caso", ["otro_servicio", "otro_conductor", "otro_tipo", "otro_destino"])
def test_una_foto_no_se_enlaza_a_un_evento_que_no_le_corresponde(
    sesion, sesion_beto, ana, beto, crear_servicio, usuario, caso
):
    servicio = crear_servicio(E.EN_CAMINO)
    otro = crear_servicio(E.EN_CAMINO)
    evento_id = str(uuid.uuid4())
    tipo = "entrega" if caso == "otro_tipo" else "recogida"
    respuesta, evidencia_id = subir(sesion, servicio, evento_id, tipo=tipo)
    assert respuesta.status_code == 201

    if caso == "otro_servicio":  # el evento con ese id llega para otro servicio
        enviar(sesion, evento_json(otro, E.RECOGIDO, id=evento_id))
    elif caso == "otro_conductor":  # lo tocó otro conductor
        enviar(sesion_beto, evento_json(servicio, E.RECOGIDO, id=evento_id))
    elif caso == "otro_tipo":  # la foto dice entrega y el evento es de recogido
        enviar(sesion, evento_json(servicio, E.RECOGIDO, id=evento_id))
    else:  # el evento no es Recogido ni Entregado
        enviar(sesion, evento_json(servicio, E.NOVEDAD, id=evento_id, motivo="Llanta pinchada"))

    assert EventoEstado.objects.filter(pk=evento_id).exists()
    evidencia = Evidencia.objects.get(pk=evidencia_id)
    assert evidencia.evento is None  # queda guardada, sin enlazar
    assert str(evidencia.evento_esperado) == evento_id


def test_una_foto_que_llega_despues_de_un_evento_que_no_le_corresponde_queda_sin_enlazar(
    sesion, crear_servicio
):
    servicio = crear_servicio(E.ASIGNADO)
    en_camino = evento_json(servicio, E.EN_CAMINO)
    enviar(sesion, en_camino)

    respuesta, evidencia_id = subir(sesion, servicio, en_camino["id"])

    assert (respuesta.status_code, respuesta.json()["enlazada"]) == (201, False)
    assert Evidencia.objects.get(pk=evidencia_id).evento is None


# --- Solo el conductor que tiene o tuvo el servicio ----------------------------------------------


def test_una_foto_para_un_servicio_que_nunca_fue_suyo_se_rechaza_sin_guardar_nada(
    sesion, beto, crear_servicio, media_temporal
):
    ajeno = crear_servicio(E.RECOGIDO, conductor=beto)

    respuesta, _ = subir(sesion, ajeno, uuid.uuid4())

    assert (respuesta.status_code, respuesta.json()) == (404, NO_ENCONTRADO)
    assert not Evidencia.objects.exists()
    assert archivos_en(media_temporal) == []
    assert not Alerta.objects.exists()


def test_una_foto_para_un_servicio_que_no_existe_responde_el_mismo_404(sesion, media_temporal):
    respuesta, _ = subir(sesion, 999_999_999, uuid.uuid4())

    assert (respuesta.status_code, respuesta.json()) == (404, NO_ENCONTRADO)
    assert archivos_en(media_temporal) == []


def test_la_foto_de_un_servicio_que_le_reasignaron_sin_que_se_enterara_se_guarda(
    sesion, ana, beto, crear_servicio, usuario
):
    """Ana recogió el vehículo sin señal; mientras tanto logística se lo pasó a Beto. Su evento
    queda en conflicto y sus fotos, que son la evidencia de lo que hizo, se guardan con él."""
    servicio = crear_servicio()
    operaciones.asignar(servicio, ana, actor=usuario)
    operaciones.reasignar(servicio, beto, actor=usuario)
    evento = evento_json(servicio, E.RECOGIDO)
    assert enviar(sesion, evento)[0]["resultado"] == "conflicto"

    respuesta, evidencia_id = subir(sesion, servicio, evento["id"])

    assert (respuesta.status_code, respuesta.json()["enlazada"]) == (201, True)
    evidencia = Evidencia.objects.get(pk=evidencia_id)
    assert (evidencia.subida_por, str(evidencia.evento_id)) == (ana, evento["id"])


def test_sin_token_no_se_suben_fotos(api, recogido, media_temporal):
    servicio, evento_id = recogido

    respuesta, _ = subir(api, servicio, evento_id)

    assert (respuesta.status_code, respuesta.json()["error"]) == (401, "no_autenticado")
    assert not Evidencia.objects.exists()
    assert archivos_en(media_temporal) == []


# --- Tamaño y tipo -------------------------------------------------------------------------------


def jpeg_de(tamano: int) -> bytes:
    return b"\xff\xd8\xff\xe0" + b"\x00" * (tamano - 4)


def test_una_foto_del_tamano_maximo_exacto_se_recibe(sesion, recogido):
    servicio, evento_id = recogido

    respuesta, evidencia_id = subir(sesion, servicio, evento_id, contenido=jpeg_de(TAMANO_MAXIMO_FOTO))

    assert respuesta.status_code == 201
    assert Evidencia.objects.get(pk=evidencia_id).tamano == TAMANO_MAXIMO_FOTO


@pytest.mark.parametrize("sobra", [1, 200 * 1024])
def test_una_foto_que_pasa_del_tamano_maximo_responde_413_y_no_guarda_nada(
    sesion, recogido, media_temporal, sobra
):
    # Con 1 byte de más la corta la escritura a disco; con 200 KB, el tamaño del cuerpo, sin leerlo.
    servicio, evento_id = recogido

    respuesta, _ = subir(
        sesion, servicio, evento_id, contenido=jpeg_de(TAMANO_MAXIMO_FOTO + sobra)
    )

    assert respuesta.status_code == 413
    assert respuesta.json() == {
        "version": 1,
        "error": "foto_demasiado_grande",
        "detalle": "La foto pesa más de 5 MB. Comprímala antes de subirla.",
        "maximo_bytes": 5 * 1024 * 1024,
    }
    assert not Evidencia.objects.exists()
    assert archivos_en(media_temporal) == []


@pytest.mark.parametrize(
    "contenido",
    [
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 100,
        b"%PDF-1.7 no es una foto",
        b"<?php echo 1; ?>",
        b"\xff\xd8",  # un JPEG cortado antes de su marca
    ],
)
def test_un_archivo_que_no_es_jpeg_se_rechaza_aunque_diga_serlo(
    sesion, recogido, media_temporal, contenido
):
    servicio, evento_id = recogido

    # El nombre y el tipo declarado dicen JPEG: se mira el contenido.
    respuesta, _ = subir(sesion, servicio, evento_id, contenido=contenido, nombre="foto.jpg")

    assert respuesta.status_code == 400
    assert respuesta.json() == {
        "version": 1,
        "error": "datos_invalidos",
        "detalle": "Revise los datos enviados.",
        "campos": {"archivo": ["La foto debe ser un JPEG."]},
    }
    assert not Evidencia.objects.exists()
    assert archivos_en(media_temporal) == []


def test_un_archivo_vacio_se_rechaza(sesion, recogido):
    servicio, evento_id = recogido

    respuesta, _ = subir(sesion, servicio, evento_id, contenido=b"")

    assert respuesta.status_code == 400
    assert "archivo" in respuesta.json()["campos"]
    assert not Evidencia.objects.exists()


@pytest.mark.parametrize(
    ("cambio", "campo"),
    [
        ({"archivo": None}, "archivo"),
        ({"archivo": "texto en vez de archivo"}, "archivo"),
        ({"tipo": "soporte"}, "tipo"),  # en la fase 1a la app solo sube recogida y entrega
        ({"tipo": "selfie"}, "tipo"),
        ({"tipo": None}, "tipo"),
        ({"evento_id": "no-es-uuid"}, "evento_id"),
        ({"servicio_id": "abc"}, "servicio_id"),
        ({"servicio_id": None}, "servicio_id"),
    ],
)
def test_una_subida_con_datos_que_faltan_o_no_valen_responde_400(
    sesion, recogido, media_temporal, cambio, campo
):
    servicio, evento_id = recogido
    otros = dict(cambio)
    evento_id = otros.pop("evento_id", evento_id)

    respuesta, _ = subir(sesion, servicio, evento_id, **otros)

    assert (respuesta.status_code, respuesta.json()["error"]) == (400, "datos_invalidos")
    assert list(respuesta.json()["campos"]) == [campo]
    assert not Evidencia.objects.exists()
    assert archivos_en(media_temporal) == []


def test_la_foto_no_se_recibe_en_json_ni_con_otro_metodo(sesion, recogido):
    servicio, evento_id = recogido
    url = url_evidencia(uuid.uuid4())

    en_json = sesion.put(url, {"servicio_id": servicio.pk, "evento_id": evento_id}, format="json")
    con_post = sesion.post(
        url, {"archivo": SimpleUploadedFile("a.jpg", JPEG)}, format="multipart"
    )

    assert (en_json.status_code, en_json.json()["error"]) == (415, "tipo_no_soportado")
    assert (con_post.status_code, con_post.json()["error"]) == (405, "metodo_no_permitido")
    assert not Evidencia.objects.exists()


def test_un_id_de_evidencia_que_no_es_uuid_no_es_una_ruta(sesion, recogido):
    servicio, evento_id = recogido
    datos = {"servicio_id": servicio.pk, "evento_id": evento_id, "tipo": "recogida",
             "archivo": SimpleUploadedFile("a.jpg", JPEG)}

    respuesta = sesion.put("/api/v1/evidencias/123/", datos, format="multipart")

    assert respuesta.status_code == 404
    assert not Evidencia.objects.exists()


# --- Nunca valores de cobro ----------------------------------------------------------------------


def test_las_respuestas_de_fotos_no_contienen_ningun_valor_de_cobro(sesion, recogido):
    servicio, evento_id = recogido
    primera, evidencia_id = subir(sesion, servicio, evento_id)
    repetida, _ = subir(sesion, servicio, evento_id, evidencia_id=evidencia_id)
    distinta, _ = subir(sesion, servicio, evento_id, evidencia_id=evidencia_id, contenido=OTRO_JPEG)

    for respuesta in (primera, repetida, distinta):
        claves = set(_claves(respuesta.json()))
        assert not {c for c in claves if any(f in c.lower() for f in FRAGMENTOS_DE_COBRO)}
