"""Tipos y documentos contra PostgreSQL: siembra por migración, coherencia tipo–sujeto en la base,
fechas, historial y que nada se edita ni se borra."""
from datetime import date

import pytest
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from documentos.models import AplicaA, Documento, DocumentoInmutable, TipoDocumento
from documentos.operaciones import DocumentoInvalido, historial, registrar_documento

pytestmark = pytest.mark.django_db

HOY = date(2026, 11, 13)


def insertar(**datos):
    """INSERT directo, sin las validaciones de `registrar_documento`: lo que decide es la base."""
    with transaction.atomic():
        Documento.objects.bulk_create([Documento(vence=HOY, **datos)])


# --- Tipos sembrados ---------------------------------------------------------------------------


def test_la_migracion_siembra_soat_y_tecnomecanica_de_grua_y_licencia_de_conductor():
    tipos = {
        (t.nombre, t.aplica_a, t.dias_anticipacion, t.activo) for t in TipoDocumento.objects.all()
    }
    assert tipos == {
        ("SOAT", AplicaA.GRUA, 30, True),
        ("Tecnomecánica", AplicaA.GRUA, 30, True),
        ("Licencia de conducción", AplicaA.CONDUCTOR, 30, True),
    }


def test_el_nombre_del_tipo_es_unico_sin_importar_mayusculas(soat):
    with pytest.raises(IntegrityError), transaction.atomic():
        TipoDocumento.objects.create(nombre="soat", aplica_a=AplicaA.CONDUCTOR)


def test_un_tipo_nuevo_avisa_por_defecto_desde_30_dias_antes():
    tipo = TipoDocumento.objects.create(nombre="Póliza de responsabilidad", aplica_a=AplicaA.GRUA)
    assert tipo.dias_anticipacion == 30


def test_el_tipo_lleva_nombre():
    with pytest.raises(IntegrityError), transaction.atomic():
        TipoDocumento.objects.create(nombre="   ", aplica_a=AplicaA.GRUA)


# --- Coherencia tipo–sujeto en la base -----------------------------------------------------------


def test_la_base_rechaza_un_documento_de_grua_con_tipo_de_conductor(licencia, grua1, quien):
    with pytest.raises(IntegrityError):
        insertar(tipo=licencia, aplica_a=AplicaA.GRUA, grua=grua1, registrado_por=quien)


def test_la_base_rechaza_un_documento_de_conductor_con_tipo_de_grua(soat, ana, quien):
    with pytest.raises(IntegrityError):
        insertar(tipo=soat, aplica_a=AplicaA.CONDUCTOR, conductor=ana, registrado_por=quien)


def test_la_base_rechaza_un_documento_en_el_lado_del_tipo_pero_con_el_otro_sujeto(
    soat, ana, quien
):
    with pytest.raises(IntegrityError):
        insertar(tipo=soat, aplica_a=AplicaA.GRUA, conductor=ana, registrado_por=quien)


def test_la_base_rechaza_un_documento_de_grua_y_conductor_a_la_vez(soat, grua1, ana, quien):
    with pytest.raises(IntegrityError):
        insertar(tipo=soat, aplica_a=AplicaA.GRUA, grua=grua1, conductor=ana, registrado_por=quien)


def test_la_base_rechaza_un_documento_sin_grua_ni_conductor(soat, quien):
    with pytest.raises(IntegrityError):
        insertar(tipo=soat, aplica_a=AplicaA.GRUA, registrado_por=quien)


def test_un_tipo_con_documentos_no_puede_cambiar_de_lado(soat, grua1, registrar):
    registrar(soat, grua1, vence_en=100)
    with pytest.raises(IntegrityError), transaction.atomic():
        TipoDocumento.objects.filter(pk=soat.pk).update(aplica_a=AplicaA.CONDUCTOR)


def test_un_tipo_sin_documentos_si_puede_cambiar_de_lado(tecnomecanica):
    TipoDocumento.objects.filter(pk=tecnomecanica.pk).update(aplica_a=AplicaA.CONDUCTOR)
    tecnomecanica.refresh_from_db()
    assert tecnomecanica.aplica_a == AplicaA.CONDUCTOR


def test_registrar_toma_el_lado_del_tipo(soat, licencia, grua1, ana, registrar):
    de_grua = registrar(soat, grua1, vence_en=10)
    de_conductor = registrar(licencia, ana, vence_en=10)
    assert (de_grua.aplica_a, de_grua.grua, de_grua.conductor) == (AplicaA.GRUA, grua1, None)
    assert (de_conductor.aplica_a, de_conductor.conductor) == (AplicaA.CONDUCTOR, ana)


def test_registrar_rechaza_un_tipo_del_otro_lado(soat, ana, registrar):
    with pytest.raises(DocumentoInvalido):
        registrar(soat, ana, vence_en=10)


def test_registrar_rechaza_un_tipo_inactivo(soat, grua1, registrar):
    soat.activo = False
    soat.save()
    with pytest.raises(DocumentoInvalido):
        registrar(soat, grua1, vence_en=10)


# --- Fechas: vence o aún no aplica ---------------------------------------------------------------


def test_la_base_exige_vencimiento_o_fecha_desde_la_que_aplica_y_no_las_dos(soat, grua1, quien):
    comun = {"tipo": soat, "aplica_a": AplicaA.GRUA, "grua": grua1, "registrado_por": quien}
    with pytest.raises(IntegrityError), transaction.atomic():
        Documento.objects.bulk_create([Documento(**comun)])
    with pytest.raises(IntegrityError), transaction.atomic():
        Documento.objects.bulk_create([Documento(vence=HOY, aplica_desde=HOY, **comun)])


def test_registrar_aun_no_aplica_guarda_la_fecha_desde_la_que_aplica(tecnomecanica, grua1, registrar):
    documento = registrar(tecnomecanica, grua1, aplica_desde_en=200)
    assert documento.aun_no_aplica
    assert documento.vence is None


def test_registrar_sin_fechas_se_rechaza(soat, grua1, registrar):
    with pytest.raises(DocumentoInvalido):
        registrar(soat, grua1)


# --- Nada se borra ni se edita; el vigente es el más reciente ------------------------------------


def test_un_documento_guardado_no_se_edita(soat, grua1, registrar):
    documento = registrar(soat, grua1, vence_en=10)
    documento.numero = "otro"
    with pytest.raises(DocumentoInmutable):
        documento.save()


def test_un_documento_no_se_puede_borrar_si_su_tipo_o_su_grua_se_borran(soat, grua1, registrar):
    registrar(soat, grua1, vence_en=10)
    with pytest.raises(ProtectedError):
        grua1.delete()
    with pytest.raises(ProtectedError):
        soat.delete()


def test_un_documento_nuevo_reemplaza_al_anterior_y_el_anterior_queda_en_el_historial(
    soat, grua1, registrar
):
    anterior = registrar(soat, grua1, vence_en=-5, numero="111")
    nuevo = registrar(soat, grua1, vence_en=365, numero="222")
    assert list(historial(soat, grua1)) == [nuevo, anterior]


def test_registrar_documento_requiere_quien_lo_registra(soat, grua1):
    with pytest.raises((IntegrityError, ValueError)), transaction.atomic():
        registrar_documento(tipo=soat, sujeto=grua1, por=None, vence=HOY)
