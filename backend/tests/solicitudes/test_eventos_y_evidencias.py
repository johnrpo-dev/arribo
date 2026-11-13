"""Los eventos de estado son de solo agregar; una evidencia no se duplica si sube dos veces."""
import uuid

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from nucleo.estados import Estado
from solicitudes import operaciones
from solicitudes.models import (
    EventoEstado,
    EventoInmutable,
    Evidencia,
    OrigenEvento,
    ResultadoEvento,
)

pytestmark = pytest.mark.django_db

E = Estado


@pytest.fixture
def evento(crear_servicio, ana, usuario):
    servicio = crear_servicio()
    return operaciones.asignar(servicio, ana, actor=usuario, motivo="Primero en la ruta")


def sin_cambios(evento):
    guardado = EventoEstado.objects.get(pk=evento.pk)
    assert (guardado.destino, guardado.motivo) == (E.ASIGNADO, "Primero en la ruta")
    assert EventoEstado.objects.count() == 1


# --- Solo agregar ------------------------------------------------------------------------------


def test_modificar_un_evento_guardado_falla(evento):
    evento.motivo = "Otro motivo"
    with pytest.raises(EventoInmutable, match="solo agregar"):
        evento.save()
    sin_cambios(evento)


def test_modificar_un_evento_leido_de_la_base_falla(evento):
    leido = EventoEstado.objects.get(pk=evento.pk)
    leido.resultado = ResultadoEvento.CONFLICTO
    with pytest.raises(EventoInmutable):
        leido.save(update_fields=["resultado"])
    sin_cambios(evento)


def test_borrar_un_evento_falla(evento):
    with pytest.raises(EventoInmutable, match="no se modifican ni se borran"):
        evento.delete()
    sin_cambios(evento)


def test_modificar_eventos_en_lote_falla(evento):
    with pytest.raises(EventoInmutable):
        EventoEstado.objects.filter(pk=evento.pk).update(motivo="x")
    with pytest.raises(EventoInmutable):
        EventoEstado.objects.all().update(resultado=ResultadoEvento.CONFLICTO)
    evento.motivo = "x"
    # bulk_update abre su transacción sin punto de guardado: se aísla para poder seguir consultando.
    with pytest.raises(EventoInmutable), transaction.atomic():
        EventoEstado.objects.bulk_update([evento], ["motivo"])
    sin_cambios(evento)


def test_borrar_eventos_en_lote_falla(evento):
    with pytest.raises(EventoInmutable):
        EventoEstado.objects.all().delete()
    with pytest.raises(EventoInmutable):
        EventoEstado.objects.filter(pk=evento.pk).delete()
    with pytest.raises(EventoInmutable):
        evento.servicio.eventos.all().delete()
    sin_cambios(evento)


def test_guardar_otro_evento_con_el_mismo_id_no_pisa_el_original(evento):
    copia = EventoEstado(
        id=evento.pk,
        servicio=evento.servicio,
        destino=E.CANCELADO,
        origen=OrigenEvento.PANEL,
        motivo="Pisado",
        resultado=ResultadoEvento.APLICADO,
    )
    with pytest.raises(IntegrityError, match="pkey"), transaction.atomic():
        copia.save()
    sin_cambios(evento)


def test_el_servicio_con_eventos_no_se_puede_borrar(evento):
    with pytest.raises(ProtectedError):
        evento.servicio.delete()


# --- Restricciones de la base del evento -------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor", "restriccion"),
    [
        ("destino", "volando", "evento_destino_valido"),
        ("origen", "correo", "evento_origen_valido"),
        ("resultado", "duplicado", "evento_resultado_valido"),
    ],
)
def test_la_base_rechaza_valores_desconocidos_en_el_evento(
    crear_servicio, campo, valor, restriccion
):
    datos = {
        "servicio": crear_servicio(),
        "destino": E.ASIGNADO,
        "origen": OrigenEvento.PANEL,
        "resultado": ResultadoEvento.APLICADO,
        campo: valor,
    }
    with pytest.raises(IntegrityError, match=restriccion), transaction.atomic():
        EventoEstado.objects.create(**datos)


# --- Evidencia ---------------------------------------------------------------------------------


@pytest.fixture
def media_temporal(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def foto(nombre="recogida.JPG"):
    return SimpleUploadedFile(nombre, b"\xff\xd8\xff fake jpeg", content_type="image/jpeg")


def test_la_evidencia_se_guarda_en_disco_con_su_tipo_y_evento(media_temporal, evento):
    id_del_celular = uuid.uuid4()
    evidencia = Evidencia.objects.create(
        id=id_del_celular,
        servicio=evento.servicio,
        evento=evento,
        tipo=Evidencia.Tipo.RECOGIDA,
        archivo=foto(),
    )
    evidencia.refresh_from_db()
    assert evidencia.archivo.name == f"evidencias/{evento.servicio_id}/{id_del_celular}.jpg"
    assert (media_temporal / evidencia.archivo.name).exists()
    assert evidencia.creada_en is not None


def test_la_misma_foto_subida_dos_veces_no_se_duplica(media_temporal, evento):
    id_del_celular = uuid.uuid4()
    datos = {
        "id": id_del_celular,
        "servicio": evento.servicio,
        "evento": evento,
        "tipo": Evidencia.Tipo.ENTREGA,
    }
    Evidencia.objects.create(archivo=foto(), **datos)
    with pytest.raises(IntegrityError, match="pkey"), transaction.atomic():
        Evidencia.objects.create(archivo=foto(), **datos)
    assert Evidencia.objects.filter(pk=id_del_celular).count() == 1


def test_la_base_rechaza_tipo_de_evidencia_desconocido(media_temporal, evento):
    with pytest.raises(IntegrityError, match="evidencia_tipo_valido"), transaction.atomic():
        Evidencia.objects.create(
            servicio=evento.servicio, evento=evento, tipo="selfie", archivo=foto()
        )


def test_un_evento_con_evidencia_no_se_puede_borrar_ni_su_servicio(media_temporal, evento):
    Evidencia.objects.create(
        servicio=evento.servicio, evento=evento, tipo=Evidencia.Tipo.SOPORTE, archivo=foto()
    )
    with pytest.raises(ProtectedError):
        evento.servicio.delete()


# --- Restricciones de la sincronización (1a-10) ------------------------------------------------


@pytest.mark.parametrize(
    ("resultado", "motivo_conflicto"),
    [
        (ResultadoEvento.APLICADO, "servicio_cancelado"),  # un aplicado no lleva motivo
        (ResultadoEvento.CONFLICTO, "porque_si"),  # motivo que no es de los conocidos
        (ResultadoEvento.CONFLICTO, "id_reutilizado"),  # es un motivo de rechazo, no de conflicto
    ],
)
def test_la_base_solo_guarda_motivo_de_conflicto_conocido_y_en_un_conflicto(
    crear_servicio, resultado, motivo_conflicto
):
    with (
        pytest.raises(IntegrityError, match="evento_motivo_solo_en_conflicto"),
        transaction.atomic(),
    ):
        EventoEstado.objects.create(
            servicio=crear_servicio(),
            destino=E.EN_CAMINO,
            origen=OrigenEvento.APP,
            resultado=resultado,
            motivo_conflicto=motivo_conflicto,
        )


def test_una_evidencia_en_espera_guarda_el_id_del_evento_que_acompana(media_temporal, evento):
    esperado = uuid.uuid4()
    evidencia = Evidencia.objects.create(
        servicio=evento.servicio,
        evento_esperado=esperado,
        tipo=Evidencia.Tipo.RECOGIDA,
        archivo=foto(),
    )
    evidencia.refresh_from_db()
    assert (evidencia.evento, evidencia.evento_esperado) == (None, esperado)


def test_la_base_rechaza_una_evidencia_sin_evento_ni_evento_en_espera(media_temporal, evento):
    with (
        pytest.raises(IntegrityError, match="evidencia_con_evento_o_en_espera"),
        transaction.atomic(),
    ):
        Evidencia.objects.create(
            servicio=evento.servicio, tipo=Evidencia.Tipo.RECOGIDA, archivo=foto()
        )


@pytest.mark.parametrize("huella", ["abc", "Z" * 64, "A" * 64])
def test_la_base_rechaza_una_huella_que_no_es_un_sha256(media_temporal, evento, huella):
    with pytest.raises(IntegrityError, match="evidencia_sha256_valido"), transaction.atomic():
        Evidencia.objects.create(
            servicio=evento.servicio,
            evento=evento,
            tipo=Evidencia.Tipo.RECOGIDA,
            archivo=foto(),
            sha256=huella,
        )


def test_el_nombre_del_archivo_no_usa_nada_del_que_manda_el_celular(media_temporal, evento):
    evidencia = Evidencia.objects.create(
        servicio=evento.servicio,
        evento=evento,
        tipo=Evidencia.Tipo.RECOGIDA,
        archivo=foto("../../malo.php"),
    )
    assert evidencia.archivo.name == f"evidencias/{evento.servicio_id}/{evidencia.pk}.jpg"
