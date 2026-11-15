"""Documentos en la sección Flota y personal contra PostgreSQL: solo administrador, estado resaltado, registrar un
documento con archivo opcional (tipo y tamaño validados, a disco con nombre del servidor),
historial y administración de tipos."""
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile, TemporaryUploadedFile
from django.test import Client

from documentos import views
from documentos.models import AplicaA, Documento, TipoDocumento
from nucleo import documentos as regla

from .conftest import en_dias

pytestmark = pytest.mark.django_db

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"foto del soat " * 50 + b"\xff\xd9"
PDF = b"%PDF-1.7\n" + b"escaneo " * 50
GIF = b"GIF89a" + b"no es foto aceptada " * 20


def url_grua(grua, tipo):
    return f"/flota/gruas/{grua.pk}/documentos/{tipo.pk}/"


def url_conductor(conductor, tipo):
    return f"/flota/conductores/{conductor.pk}/documentos/{tipo.pk}/"


@pytest.fixture
def media(settings, tmp_path):
    """Los archivos de la prueba van a una carpeta temporal, no a `backend/media/`."""
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def administrador(client, crear_usuario):
    usuario = crear_usuario("administrador", first_name="Olga")
    client.force_login(usuario)
    return usuario


def datos_vence(dias=365, **otros):
    return {"situacion": "vence", "vence": en_dias(dias).isoformat(), "numero": "", **otros}


def archivos_en(carpeta):
    return [p for p in carpeta.rglob("*") if p.is_file()]


# --- Permisos ------------------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["logistica", "facturacion"])
def test_logistica_y_facturacion_no_entran_a_flota_ni_a_documentos(
    client, crear_usuario, rol, soat, grua1, registrar, media
):
    documento = registrar(soat, grua1, vence_en=10, archivo=SimpleUploadedFile("a.jpg", JPEG),
                          tipo_archivo="jpeg")
    client.force_login(crear_usuario(rol))
    for ruta in (
        "/flota/",
        url_grua(grua1, soat),
        f"/flota/documentos/{documento.pk}/archivo/",
        "/flota/tipos/",
        f"/flota/tipos/{soat.pk}/",
    ):
        assert client.get(ruta).status_code == 403, ruta
    assert client.post(url_grua(grua1, soat), datos_vence()).status_code == 403
    assert client.post("/flota/tipos/", {"nombre": "Otro", "aplica_a": "grua",
                                         "dias_anticipacion": 5}).status_code == 403
    assert Documento.objects.count() == 1
    assert not TipoDocumento.objects.filter(nombre="Otro").exists()


def test_sin_sesion_flota_lleva_al_ingreso(client, soat, grua1):
    for ruta in ("/flota/", url_grua(grua1, soat), "/flota/tipos/"):
        respuesta = client.get(ruta)
        assert respuesta.status_code == 302
        assert respuesta["Location"].startswith("/ingresar/")


def test_la_seccion_flota_ya_no_dice_aun_no_disponible(client, administrador):
    html = client.get("/flota/").content.decode()
    assert "Aún no disponible" not in html
    assert '<h1 class="titulo-pagina">Flota y personal</h1>' in html


# --- Lista ---------------------------------------------------------------------------------------


def fila_de(html, enlace):
    """El HTML de la fila de la tabla que lleva a `enlace`."""
    inicio = html.index(enlace)
    return html[inicio:html.index("</tr>", inicio)]


def test_la_lista_resume_los_documentos_de_cada_uno_con_las_etiquetas_de_estado(
    client, administrador, soat, tecnomecanica, licencia, ana, beto, grua1, grua2, registrar
):
    registrar(soat, grua1, vence_en=-1)
    registrar(tecnomecanica, grua1, vence_en=200)
    registrar(soat, grua2, vence_en=10)
    registrar(tecnomecanica, grua2, vence_en=200)
    registrar(licencia, ana, vence_en=400)

    html = client.get("/flota/").content.decode()

    assert "Hay 1 documento vencido" in html
    assert "Hay 1 documento por vencer" in html
    grua_vencida = fila_de(html, f'href="/flota/gruas/{grua1.pk}/"')
    assert '<span class="estado estado--novedad">Vencido</span>' in grua_vencida
    assert "SOAT" in grua_vencida
    grua_por_vencer = fila_de(html, f'href="/flota/gruas/{grua2.pk}/"')
    assert '<span class="estado estado--recogido">Por vencer</span>' in grua_por_vencer
    al_dia = fila_de(html, f'href="/flota/conductores/{ana.pk}/"')
    assert '<span class="estado estado--entregado">Al día</span>' in al_dia
    sin_licencia = fila_de(html, f'href="/flota/conductores/{beto.pk}/"')
    assert '<span class="estado estado--pendiente_asignar">Falta</span>' in sin_licencia
    assert "Licencia de conducción" in sin_licencia


def test_la_pagina_de_la_grua_muestra_cada_documento_y_enlaza_a_registrarlo(
    client, administrador, soat, tecnomecanica, grua1, registrar
):
    registrar(soat, grua1, vence_en=-1)

    html = client.get(f"/flota/gruas/{grua1.pk}/").content.decode()

    assert '<span class="estado estado--novedad">Vencido</span>' in html
    assert '<span class="estado estado--pendiente_asignar">Falta</span>' in html
    assert url_grua(grua1, soat) in html
    assert url_grua(grua1, tecnomecanica) in html
    assert "Quien maneje esta grúa no recibe servicios nuevos" in html


def test_la_pagina_del_conductor_muestra_sus_documentos_y_si_esta_bloqueado(
    client, administrador, licencia, soat, ana, beto, grua1, registrar
):
    registrar(licencia, ana, vence_en=400)
    registrar(soat, grua1, vence_en=-3)  # la grúa de Ana

    ana_html = client.get(f"/flota/conductores/{ana.pk}/").content.decode()
    beto_html = client.get(f"/flota/conductores/{beto.pk}/").content.decode()

    assert '<span class="estado estado--entregado">Vigente</span>' in ana_html
    assert url_conductor(ana, licencia) in ana_html
    assert "No recibe servicios nuevos" in ana_html
    assert "SOAT de la grúa GRU001" in ana_html
    assert '<span class="estado estado--pendiente_asignar">Falta</span>' in beto_html
    assert "No recibe servicios nuevos" not in beto_html


def test_el_documento_vuelve_a_la_pagina_de_su_conductor_o_su_grua(
    client, administrador, soat, licencia, ana, grua1
):
    assert f'href="/flota/conductores/{ana.pk}/"' in client.get(
        url_conductor(ana, licencia)
    ).content.decode()
    assert f'href="/flota/gruas/{grua1.pk}/"' in client.get(url_grua(grua1, soat)).content.decode()


def test_un_tipo_inactivo_no_se_exige_ni_en_la_lista_ni_en_la_grua(
    client, administrador, tecnomecanica, grua1
):
    assert "Tecnomecánica" in client.get("/flota/").content.decode()  # falta, mientras esté activo
    tecnomecanica.activo = False
    tecnomecanica.save()
    assert "Tecnomecánica" not in client.get("/flota/").content.decode()
    assert "Tecnomecánica" not in client.get(f"/flota/gruas/{grua1.pk}/").content.decode()


# --- Registrar e historial -----------------------------------------------------------------------


def test_registrar_un_documento_sin_archivo(client, administrador, soat, grua1):
    respuesta = client.post(url_grua(grua1, soat), datos_vence(200, numero=" 123-ABC "))
    assert respuesta.status_code == 302
    documento = Documento.objects.get()
    assert (documento.grua, documento.tipo, documento.numero) == (grua1, soat, "123-ABC")
    assert documento.vence == en_dias(200)
    assert documento.registrado_por == administrador
    assert not documento.archivo


def test_registrar_aun_no_aplica_exige_la_fecha_desde_la_que_aplica(
    client, administrador, tecnomecanica, grua1
):
    datos = {"situacion": "aun_no_aplica", "vence": en_dias(10).isoformat(), "aplica_desde": ""}
    respuesta = client.post(url_grua(grua1, tecnomecanica), datos)
    assert respuesta.status_code == 200
    assert "Escriba la fecha desde la que aplica." in respuesta.content.decode()
    assert not Documento.objects.exists()

    datos["aplica_desde"] = en_dias(300).isoformat()
    assert client.post(url_grua(grua1, tecnomecanica), datos).status_code == 302
    documento = Documento.objects.get()
    assert (documento.vence, documento.aplica_desde) == (None, en_dias(300))


def test_registrar_sin_fecha_de_vencimiento_se_rechaza(client, administrador, licencia, ana):
    respuesta = client.post(url_conductor(ana, licencia), {"situacion": "vence", "vence": ""})
    assert "Escriba la fecha de vencimiento." in respuesta.content.decode()
    assert not Documento.objects.exists()


def test_un_tipo_de_grua_no_se_abre_para_un_conductor(client, administrador, soat, ana):
    assert client.get(url_conductor(ana, soat)).status_code == 404
    assert client.post(url_conductor(ana, soat), datos_vence()).status_code == 404


def test_el_historial_muestra_el_vigente_y_los_reemplazados(
    client, administrador, licencia, ana, registrar
):
    registrar(licencia, ana, vence_en=-30, numero="VIEJA")
    registrar(licencia, ana, vence_en=900, numero="NUEVA")

    html = client.get(url_conductor(ana, licencia)).content.decode()

    assert html.index("NUEVA") < html.index("VIEJA")
    assert "Vigente" in html and "Reemplazado" in html
    assert '<span class="estado estado--entregado">Vigente</span>' in html


# --- Archivo -------------------------------------------------------------------------------------


def test_registrar_con_foto_la_guarda_en_disco_con_nombre_del_servidor(
    client, administrador, soat, grua1, media
):
    foto = SimpleUploadedFile("../../SOAT de la grua.jpg", JPEG, content_type="image/jpeg")
    respuesta = client.post(url_grua(grua1, soat), {**datos_vence(), "archivo": foto})

    assert respuesta.status_code == 302
    documento = Documento.objects.get()
    assert documento.tipo_archivo == "jpeg"
    assert documento.archivo.name.startswith(f"documentos/grua/{grua1.pk}/")
    assert documento.archivo.name.endswith(".jpg")
    assert "SOAT" not in documento.archivo.name
    assert [p.read_bytes() for p in archivos_en(media)] == [JPEG]

    vista = client.get(f"/flota/documentos/{documento.pk}/archivo/")
    assert vista.status_code == 200
    assert vista["Content-Type"] == "image/jpeg"
    assert b"".join(vista.streaming_content) == JPEG


def test_un_pdf_se_acepta_y_la_extension_sale_del_contenido(
    client, administrador, licencia, ana, media
):
    escaneo = SimpleUploadedFile("licencia.jpg", PDF, content_type="image/jpeg")
    client.post(url_conductor(ana, licencia), {**datos_vence(), "archivo": escaneo})
    documento = Documento.objects.get()
    assert (documento.tipo_archivo, documento.archivo.name[-4:]) == ("pdf", ".pdf")


def test_un_archivo_de_tipo_no_aceptado_se_rechaza_y_no_queda_nada(
    client, administrador, soat, grua1, media
):
    gif = SimpleUploadedFile("soat.jpg", GIF, content_type="image/jpeg")
    respuesta = client.post(url_grua(grua1, soat), {**datos_vence(), "archivo": gif})

    assert respuesta.status_code == 200
    assert "El archivo debe ser una foto JPEG o PNG, o un PDF." in respuesta.content.decode()
    assert not Documento.objects.exists()
    assert archivos_en(media) == []


def test_un_archivo_que_pasa_del_tamano_maximo_se_rechaza_y_no_queda_nada(
    client, administrador, soat, grua1, media, monkeypatch
):
    monkeypatch.setattr(regla, "TAMANO_MAXIMO_ARCHIVO", 1024)
    grande = SimpleUploadedFile("soat.jpg", JPEG + b"x" * 5000, content_type="image/jpeg")
    respuesta = client.post(url_grua(grua1, soat), {**datos_vence(), "archivo": grande})

    assert respuesta.status_code == 200
    assert "El archivo pesa más de" in respuesta.content.decode()
    assert not Documento.objects.exists()
    assert archivos_en(media) == []


def test_el_archivo_llega_en_disco_y_no_en_memoria_aunque_sea_pequeno(
    client, administrador, soat, grua1, media, monkeypatch
):
    recibidos = []
    original = views.registrar_documento

    def espiar(**datos):
        recibidos.append(datos["archivo"])
        return original(**datos)

    monkeypatch.setattr(views, "registrar_documento", espiar)
    client.post(url_grua(grua1, soat), {**datos_vence(), "archivo": SimpleUploadedFile("a.jpg", JPEG)})

    assert len(recibidos) == 1
    assert isinstance(recibidos[0], TemporaryUploadedFile)


def test_registrar_con_archivo_sigue_exigiendo_el_token_csrf(crear_usuario, soat, grua1, media):
    cliente = Client(enforce_csrf_checks=True)
    cliente.force_login(crear_usuario("administrador"))
    respuesta = cliente.post(
        url_grua(grua1, soat), {**datos_vence(), "archivo": SimpleUploadedFile("a.jpg", JPEG)}
    )
    assert respuesta.status_code == 403
    assert not Documento.objects.exists()
    assert archivos_en(media) == []


# --- Tipos de documento --------------------------------------------------------------------------


def test_crear_un_tipo_de_documento(client, administrador):
    respuesta = client.post(
        "/flota/tipos/",
        {"nombre": "  Póliza   de responsabilidad ", "aplica_a": "grua",
         "dias_anticipacion": 45, "activo": "on"},
    )
    assert respuesta.status_code == 302
    tipo = TipoDocumento.objects.get(nombre="Póliza de responsabilidad")
    assert (tipo.aplica_a, tipo.dias_anticipacion, tipo.activo) == (AplicaA.GRUA, 45, True)
    assert "Póliza de responsabilidad" in client.get("/flota/").content.decode()


def test_un_tipo_con_nombre_repetido_se_rechaza(client, administrador, soat):
    respuesta = client.post(
        "/flota/tipos/", {"nombre": "soat", "aplica_a": "grua", "dias_anticipacion": 30}
    )
    assert respuesta.status_code == 200
    assert "Ya hay un tipo de documento con ese nombre." in respuesta.content.decode()


def test_editar_los_dias_de_anticipacion_y_desactivar_un_tipo(client, administrador, soat):
    respuesta = client.post(
        f"/flota/tipos/{soat.pk}/",
        {"nombre": "SOAT", "aplica_a": "grua", "dias_anticipacion": 15},  # sin "activo"
    )
    assert respuesta.status_code == 302
    soat.refresh_from_db()
    assert (soat.dias_anticipacion, soat.activo) == (15, False)


def test_un_tipo_con_documentos_no_cambia_de_lado_desde_la_pantalla(
    client, administrador, soat, grua1, registrar
):
    registrar(soat, grua1, vence_en=10)
    html = client.get(f"/flota/tipos/{soat.pk}/").content.decode()
    assert "no cambia de lado" in html
    assert "---------" not in html

    client.post(
        f"/flota/tipos/{soat.pk}/",
        {"nombre": "SOAT", "aplica_a": "conductor", "dias_anticipacion": 30, "activo": "on"},
    )
    soat.refresh_from_db()
    assert soat.aplica_a == AplicaA.GRUA


def test_dias_de_anticipacion_negativos_se_rechazan(client, administrador, soat):
    respuesta = client.post(
        f"/flota/tipos/{soat.pk}/",
        {"nombre": "SOAT", "aplica_a": "grua", "dias_anticipacion": -1, "activo": "on"},
    )
    assert respuesta.status_code == 200
    soat.refresh_from_db()
    assert soat.dias_anticipacion == 30


def test_un_tipo_inactivo_muestra_el_historial_pero_no_deja_registrar(
    client, administrador, soat, grua1, registrar
):
    registrar(soat, grua1, vence_en=10, numero="999")
    soat.activo = False
    soat.save()
    respuesta = client.get(url_grua(grua1, soat))
    html = respuesta.content.decode()
    assert "999" in html
    assert "Registrar documento nuevo" not in html
    client.post(url_grua(grua1, soat), datos_vence())
    assert Documento.objects.count() == 1
