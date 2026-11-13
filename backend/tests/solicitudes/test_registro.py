"""Registro de solicitud desde el panel: acceso, búsqueda por teléfono, cliente nuevo, borrador o
abierta, pagador, contactos, vehículo, hora programada y que un error a mitad no deje nada.
"""
from datetime import UTC, datetime

import pytest

from clientes.models import Cliente, Contacto, TelefonoCliente, TipoCliente
from nucleo.estados import Estado
from nucleo.registro import Faltante
from solicitudes import registro
from solicitudes.models import EstadoRegistro, Servicio, Solicitud, Vehiculo
from solicitudes.registro import DatosRegistro, DatosVehiculo, registrar_solicitud
from tests.conftest import VIN

pytestmark = pytest.mark.django_db

RUTA = "/solicitudes/nueva/"
BUSCAR = "/solicitudes/nueva/cliente/"


def datos(**cambios):
    """Lo que manda el formulario para un traslado completo de un cliente ya registrado."""
    base = {
        "telefono": "300 123 4567",
        "tipo": "traslado",
        "origen": "Calle 10 # 43-20, El Poblado",
        "contacto_origen_nombre": "Luisa",
        "contacto_origen_telefono": "311 222 3344",
        "destino": "Carrera 70 # 1-50, Belén",
        "placa": "abc-123",
        "marca": "Mazda",
        "linea": "3",
        "color": "Gris",
        "accion": "guardar",
    }
    base.update(cambios)
    return formulario({k: v for k, v in base.items() if v is not None})


CAMPOS_VEHICULO = ("servicio", "placa", "vin", "marca", "linea", "color", "referencia_externa", "quitar")


def formulario(campos, vehiculos=None):
    """Lo que manda el navegador: los campos del vehículo van en la fila 0 del conjunto de
    vehículos (o en las filas de `vehiculos`), con su formulario de control."""
    filas = vehiculos if vehiculos is not None else [
        {c: campos.pop(c) for c in CAMPOS_VEHICULO if c in campos}
    ]
    for c in CAMPOS_VEHICULO:
        campos.pop(c, None)
    campos["vehiculos-TOTAL_FORMS"] = str(len(filas))
    campos["vehiculos-INITIAL_FORMS"] = "0"
    for i, fila in enumerate(filas):
        for clave, valor in fila.items():
            campos[f"vehiculos-{i}-{clave}"] = valor
    return campos


@pytest.fixture
def con_telefono(cliente):
    TelefonoCliente.objects.create(cliente=cliente, numero="3001234567")
    return cliente


@pytest.fixture
def logistica(client, crear_usuario):
    usuario = crear_usuario("logistica")
    client.force_login(usuario)
    return usuario


# --- Acceso ------------------------------------------------------------------------------------


@pytest.mark.parametrize("rol", ["logistica", "administrador"])
def test_logistica_y_administrador_abren_el_formulario(client, crear_usuario, rol):
    client.force_login(crear_usuario(rol))
    respuesta = client.get(RUTA)
    assert respuesta.status_code == 200
    html = respuesta.content.decode()
    assert '<h1 class="titulo-pagina">Nueva solicitud</h1>' in html
    assert "Aún no disponible" not in html


@pytest.mark.parametrize("ruta", [RUTA, BUSCAR + "?telefono=3001234567", "/solicitudes/1/"])
def test_facturacion_recibe_403(client, crear_usuario, ruta):
    client.force_login(crear_usuario("facturacion"))
    assert client.get(ruta).status_code == 403


def test_facturacion_no_puede_registrar(client, crear_usuario, con_telefono):
    client.force_login(crear_usuario("facturacion"))
    assert client.post(RUTA, datos()).status_code == 403
    assert Solicitud.objects.count() == 0


@pytest.mark.parametrize("ruta", [RUTA, BUSCAR, "/solicitudes/1/"])
def test_sin_sesion_lleva_al_ingreso(client, ruta):
    respuesta = client.get(ruta)
    assert respuesta.status_code == 302
    assert respuesta["Location"].startswith("/ingresar/?next=")


def test_el_foco_inicial_esta_en_el_telefono(client, logistica):
    html = client.get(RUTA).content.decode()
    primer_campo = html.index('name="telefono"')
    assert "autofocus" in html[html.rindex("<input", 0, primer_campo):html.index(">", primer_campo)]
    assert html.index('name="telefono"') < html.index('name="tipo"') < html.index('name="origen"')


# --- Búsqueda por teléfono ---------------------------------------------------------------------


@pytest.mark.parametrize("digitado", ["3001234567", "300 123 4567", "+57 300 123 4567", "300-123-4567"])
def test_buscar_por_telefono_encuentra_con_cualquier_formato(client, logistica, con_telefono, digitado):
    html = client.get(BUSCAR, {"telefono": digitado, "para": "solicitante"}).content.decode()
    assert "Autos del Valle" in html
    assert "nuevo_nombre" not in html


def test_buscar_muestra_el_historial_reciente_del_cliente(client, logistica, con_telefono):
    from tests.conftest import crear_solicitud

    for numero in range(7):
        crear_solicitud(con_telefono, origen=f"Origen {numero}")
    html = client.get(BUSCAR, {"telefono": "3001234567"}).content.decode()
    assert "Últimas solicitudes" in html
    assert html.count("<tr>") - 1 == registro.FILAS_HISTORIAL  # una fila es el encabezado
    assert "Origen 6" in html  # la más reciente
    assert "Origen 0" not in html


def test_buscar_un_telefono_desconocido_ofrece_crear_el_cliente(client, logistica):
    html = client.get(BUSCAR, {"telefono": "310 555 0000"}).content.decode()
    assert "No hay ningún cliente con ese teléfono" in html
    assert 'name="nuevo_nombre"' in html
    assert 'name="nuevo_tipo"' in html


def test_buscar_un_telefono_incompleto_no_muestra_nada(client, logistica):
    html = client.get(BUSCAR, {"telefono": "300"}).content.decode()
    assert html.strip() == ""


def test_buscar_pagador_muestra_quien_paga(client, logistica, con_telefono):
    html = client.get(BUSCAR, {"pagador_telefono": "+57 3001234567", "para": "pagador"})
    assert "Paga <strong>Autos del Valle</strong>" in html.content.decode()


# --- Guardar -----------------------------------------------------------------------------------


def test_solicitud_completa_queda_abierta_con_servicio_pendiente_de_asignar(
    client, logistica, con_telefono
):
    respuesta = client.post(RUTA, datos(), follow=True)
    solicitud = Solicitud.objects.get()
    assert respuesta.redirect_chain == [(f"/solicitudes/{solicitud.pk}/", 302)]
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA
    assert solicitud.solicitante == con_telefono
    assert solicitud.creada_por == logistica
    servicio = solicitud.servicios.get()
    assert servicio.estado == Estado.PENDIENTE_ASIGNAR
    assert (servicio.vehiculo.placa, servicio.vehiculo.marca) == ("ABC123", "Mazda")
    html = respuesta.content.decode()
    assert "Queda abierta" in html
    assert "Abierta" in html
    assert '<span class="estado estado--pendiente_asignar">Pendiente de asignar</span>' in html


def test_solicitud_incompleta_queda_en_borrador_y_dice_que_falta(client, logistica, con_telefono):
    sin_vehiculo = {"placa": "", "marca": "", "linea": "", "color": ""}
    respuesta = client.post(RUTA, datos(origen="", destino="", **sin_vehiculo), follow=True)
    solicitud = Solicitud.objects.get()
    assert solicitud.estado_registro == EstadoRegistro.BORRADOR
    assert not solicitud.servicios.exists()
    html = respuesta.content.decode()
    assert "guardada como borrador" in html
    assert "falta el origen, el destino y al menos un vehículo" in html


def test_borrador_con_vehiculo_conserva_el_vehiculo(client, logistica, con_telefono):
    client.post(RUTA, datos(destino=""))
    solicitud = Solicitud.objects.get()
    assert solicitud.estado_registro == EstadoRegistro.BORRADOR
    assert solicitud.servicios.get().vehiculo.placa == "ABC123"


def test_guardar_como_borrador_deja_borrador_aunque_este_completa(client, logistica, con_telefono):
    respuesta = client.post(RUTA, datos(accion="borrador"), follow=True)
    assert Solicitud.objects.get().estado_registro == EstadoRegistro.BORRADOR
    assert "guardada como borrador" in respuesta.content.decode()


def test_desvare_sin_destino_queda_abierto(client, logistica, con_telefono):
    client.post(RUTA, datos(tipo="desvare", destino=""))
    assert Solicitud.objects.get().estado_registro == EstadoRegistro.ABIERTA


def test_traslado_sin_destino_queda_en_borrador(client, logistica, con_telefono):
    client.post(RUTA, datos(destino=""))
    assert Solicitud.objects.get().estado_registro == EstadoRegistro.BORRADOR


def test_evento_queda_en_borrador_hasta_responder_el_regreso(client, logistica, con_telefono):
    respuesta = client.post(RUTA, datos(tipo="evento"), follow=True)
    assert Solicitud.objects.get().estado_registro == EstadoRegistro.BORRADOR
    assert "la respuesta de si el evento tiene regreso" in respuesta.content.decode()


def test_sin_tipo_no_se_guarda_y_el_error_queda_junto_al_campo(client, logistica, con_telefono):
    respuesta = client.post(RUTA, datos(tipo=""))
    assert respuesta.status_code == 200
    assert "Elija el tipo de servicio." in respuesta.content.decode()
    assert Solicitud.objects.count() == 0


def test_sin_telefono_no_se_guarda(client, logistica):
    respuesta = client.post(RUTA, datos(telefono=""))
    assert "Escriba el teléfono de quien llama." in respuesta.content.decode()
    assert Solicitud.objects.count() == 0


# --- Cliente nuevo -----------------------------------------------------------------------------


def test_crear_cliente_nuevo_desde_el_formulario(client, logistica):
    client.post(
        RUTA,
        datos(telefono="+57 310 555 0000", nuevo_nombre="Pedro Pérez", nuevo_tipo="particular"),
    )
    cliente = Cliente.objects.get()
    assert (cliente.nombre, cliente.tipo) == ("Pedro Pérez", TipoCliente.PARTICULAR)
    assert cliente.telefonos.get().numero == "3105550000"
    solicitud = Solicitud.objects.get()
    assert solicitud.solicitante == cliente
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA


def test_cliente_nuevo_sin_nombre_ni_tipo_marca_los_dos_campos(client, logistica):
    respuesta = client.post(RUTA, datos(telefono="310 555 0000"))
    html = respuesta.content.decode()
    assert "Escriba el nombre del cliente nuevo." in html
    assert "Elija el tipo de cliente." in html
    assert Cliente.objects.count() == 0
    assert Solicitud.objects.count() == 0


def test_con_cliente_existente_no_se_crea_otro(client, logistica, con_telefono):
    client.post(RUTA, datos(nuevo_nombre="Otro nombre", nuevo_tipo="particular"))
    assert Cliente.objects.count() == 1


def test_un_error_a_mitad_no_deja_cliente_ni_solicitud(client, logistica, monkeypatch):
    def falla(*args, **kwargs):
        raise RuntimeError("falla simulada al crear el servicio")

    monkeypatch.setattr(registro, "_crear_servicio", falla)
    client.raise_request_exception = True
    with pytest.raises(RuntimeError):
        client.post(
            RUTA, datos(telefono="310 555 0000", nuevo_nombre="Pedro", nuevo_tipo="particular")
        )
    assert Cliente.objects.count() == 0
    assert TelefonoCliente.objects.count() == 0
    assert Contacto.objects.count() == 0
    assert Vehiculo.objects.count() == 0
    assert Solicitud.objects.count() == 0


def test_registrar_se_deshace_entero_si_falla_al_final(monkeypatch, usuario):
    def falla(*args, **kwargs):
        raise RuntimeError("falla simulada")

    monkeypatch.setattr(registro, "_crear_servicio", falla)
    nuevo = registro.ClienteNuevo("Pedro", TipoCliente.PARTICULAR, "3105550000")
    with pytest.raises(RuntimeError):
        registrar_solicitud(
            DatosRegistro(
                tipo="traslado",
                cliente_nuevo=nuevo,
                origen="A",
                destino="B",
                vehiculos=(DatosVehiculo("XYZ789", ""),),
            ),
            usuario=usuario,
        )
    assert Cliente.objects.count() == Vehiculo.objects.count() == Solicitud.objects.count() == 0


# --- Pagador -----------------------------------------------------------------------------------


def test_el_pagador_por_defecto_es_el_solicitante(client, logistica, con_telefono):
    client.post(RUTA, datos())
    solicitud = Solicitud.objects.get()
    assert solicitud.pagador == solicitud.solicitante == con_telefono


def test_el_pagador_puede_ser_otro_cliente_buscado_por_telefono(client, logistica, con_telefono):
    aseguradora = Cliente.objects.create(nombre="Seguros Andinos", tipo=TipoCliente.ASEGURADORA)
    TelefonoCliente.objects.create(cliente=aseguradora, numero="6045551234")
    client.post(RUTA, datos(pagador_telefono="604 555 1234"))
    solicitud = Solicitud.objects.get()
    assert solicitud.solicitante == con_telefono
    assert solicitud.pagador == aseguradora


def test_pagador_desconocido_no_se_guarda(client, logistica, con_telefono):
    respuesta = client.post(RUTA, datos(pagador_telefono="604 555 9999"))
    assert "No hay ningún cliente con ese teléfono." in respuesta.content.decode()
    assert Solicitud.objects.count() == 0


# --- Contactos ---------------------------------------------------------------------------------


def test_el_contacto_se_crea_normalizado_y_se_reutiliza(client, logistica, con_telefono):
    client.post(RUTA, datos())
    client.post(RUTA, datos(contacto_origen_telefono="+57 311-222-3344", placa="XYZ789"))
    contacto = Contacto.objects.get()
    assert (contacto.nombre, contacto.telefono) == ("Luisa", "3112223344")
    assert set(Solicitud.objects.values_list("contacto_origen", flat=True)) == {contacto.pk}


def test_contacto_con_nombre_y_sin_telefono_marca_el_telefono(client, logistica, con_telefono):
    respuesta = client.post(RUTA, datos(contacto_destino_nombre="Jorge"))
    assert "Escriba el teléfono del contacto." in respuesta.content.decode()
    assert Solicitud.objects.count() == 0


def test_contacto_con_telefono_y_sin_nombre_marca_el_nombre(client, logistica, con_telefono):
    respuesta = client.post(RUTA, datos(contacto_origen_nombre=""))
    assert "Escriba el nombre del contacto." in respuesta.content.decode()


# --- Vehículo ----------------------------------------------------------------------------------


def test_vin_invalido_se_rechaza_junto_al_campo(client, logistica, con_telefono):
    respuesta = client.post(RUTA, datos(vin="1HGCM82633A0O4352"))
    assert "sin I, O ni Q" in respuesta.content.decode()
    assert Solicitud.objects.count() == 0


def test_placa_y_vin_se_guardan_normalizados(client, logistica, con_telefono):
    client.post(RUTA, datos(placa="abc 123", vin="1hg-cm826 33a004352"))
    vehiculo = Vehiculo.objects.get()
    assert (vehiculo.placa, vehiculo.vin) == ("ABC123", VIN)


def test_solo_vin_sin_placa_en_traslado_queda_abierta(client, logistica, con_telefono):
    client.post(RUTA, datos(placa="", vin=VIN))
    assert Solicitud.objects.get().estado_registro == EstadoRegistro.ABIERTA


def test_vehiculo_sin_placa_ni_vin_cuenta_si_tiene_otros_datos(client, logistica, con_telefono):
    # La placa o el VIN se exigen al recoger (y en la 1a-07, según la configuración), no aquí.
    client.post(RUTA, datos(placa=""))
    solicitud = Solicitud.objects.get()
    assert solicitud.estado_registro == EstadoRegistro.ABIERTA
    assert solicitud.servicios.get().vehiculo.marca == "Mazda"


def test_vehiculo_ya_registrado_se_reutiliza_y_completa(client, logistica, con_telefono, nuevo_vehiculo):
    existente = nuevo_vehiculo(placa="ABC123")
    client.post(RUTA, datos(vin=VIN))
    assert Vehiculo.objects.count() == 1
    existente.refresh_from_db()
    assert (existente.vin, existente.marca) == (VIN, "Mazda")
    assert Servicio.objects.get().vehiculo == existente


def test_placa_y_vin_de_vehiculos_distintos_se_rechazan(client, logistica, con_telefono, nuevo_vehiculo):
    nuevo_vehiculo(placa="ABC123")
    nuevo_vehiculo(placa="XYZ789", vin=VIN)
    respuesta = client.post(RUTA, datos(vin=VIN))
    assert "Ese VIN ya es del vehículo XYZ789" in respuesta.content.decode()
    assert Solicitud.objects.count() == 0


# --- Programada --------------------------------------------------------------------------------


def test_hora_programada_se_guarda_en_utc_desde_la_hora_de_colombia(client, logistica, con_telefono):
    client.post(RUTA, datos(programada_para="2026-11-20T14:30"))
    programada = Solicitud.objects.get().programada_para
    assert programada == datetime(2026, 11, 20, 19, 30, tzinfo=UTC)


def test_sin_hora_programada_es_inmediato(client, logistica, con_telefono):
    respuesta = client.post(RUTA, datos(), follow=True)
    assert Solicitud.objects.get().programada_para is None
    assert "Inmediato" in respuesta.content.decode()


def test_hora_programada_incompleta_se_rechaza(client, logistica, con_telefono):
    respuesta = client.post(RUTA, datos(programada_para="2026-11-20"))
    assert "Escriba la fecha y la hora completas." in respuesta.content.decode()
    assert Solicitud.objects.count() == 0


# --- Detalle -----------------------------------------------------------------------------------


def test_detalle_de_un_borrador_dice_que_falta(client, logistica, cliente):
    from tests.conftest import crear_solicitud

    solicitud = crear_solicitud(cliente, destino="", estado_registro=EstadoRegistro.BORRADOR)
    html = client.get(f"/solicitudes/{solicitud.pk}/").content.decode()
    assert "Borrador. Para abrirla falta el destino y al menos un vehículo." in html


def test_detalle_de_una_solicitud_que_no_existe_da_404(client, logistica):
    assert client.get("/solicitudes/999999/").status_code == 404


def test_faltantes_de_una_solicitud_guardada(cliente):
    from tests.conftest import crear_solicitud

    solicitud = crear_solicitud(cliente, origen="", estado_registro=EstadoRegistro.BORRADOR)
    assert registro.faltantes_de(solicitud) == [Faltante.ORIGEN, Faltante.VEHICULO]
