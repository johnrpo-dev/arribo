"""Panel del dueño (1a-19) contra PostgreSQL, con datos conocidos: servicios del periodo por estado,
no concretadas por motivo, lo pendiente de cobro por pagador y los documentos por vencer."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from clientes.models import Cliente, TipoCliente
from cobros.models import LineaCobro
from documentos.consultas import dia_local
from documentos.models import TipoDocumento
from documentos.operaciones import registrar_documento
from nucleo.estados import Estado
from panel.dueno import (
    cobros_por_pagador,
    datos_del_panel,
    no_concretadas_por_motivo,
    servicios_por_estado,
)
from solicitudes.models import EstadoRegistro, Solicitud
from tests.conftest import crear_solicitud

pytestmark = pytest.mark.django_db

DIA = date(2026, 11, 18)
DIA_19 = date(2026, 11, 19)
# 18/11 a las 15:00 en Medellín (20:00 UTC); 19/11 a las 2:00 UTC aún es 18/11 en Medellín.
A_MEDIODIA = datetime(2026, 11, 18, 20, 0, tzinfo=UTC)
NOCHE_DEL_18 = datetime(2026, 11, 19, 2, 0, tzinfo=UTC)
DIA_SIGUIENTE = datetime(2026, 11, 19, 15, 0, tzinfo=UTC)


def registrada_el(solicitud, momento):
    Solicitud.objects.filter(pk=solicitud.pk).update(creada_en=momento)
    return solicitud


def cuenta(filas) -> dict:
    return {estado: n for estado, _, n in filas}


def test_servicios_del_dia_por_estado(cliente, crear_servicio):
    inmediata = registrada_el(crear_solicitud(cliente), A_MEDIODIA)
    crear_servicio(Estado.ENTREGADO, solicitud_de=inmediata)
    crear_servicio(Estado.ENTREGADO, solicitud_de=inmediata)
    crear_servicio(Estado.EN_CAMINO, solicitud_de=inmediata)
    de_noche = registrada_el(crear_solicitud(cliente), NOCHE_DEL_18)  # en Colombia, aún el 18
    crear_servicio(solicitud_de=de_noche)
    # Registrada el 18 pero programada para el 19: es del 19.
    programada = registrada_el(crear_solicitud(cliente, programada_para=DIA_SIGUIENTE), A_MEDIODIA)
    crear_servicio(solicitud_de=programada)
    # Un borrador del día no cuenta.
    borrador = registrada_el(
        crear_solicitud(cliente, estado_registro=EstadoRegistro.BORRADOR), A_MEDIODIA
    )
    crear_servicio(solicitud_de=borrador)

    assert cuenta(servicios_por_estado(DIA, DIA)) == {
        "pendiente_asignar": 1,
        "asignado": 0,
        "en_camino": 1,
        "recogido": 0,
        "entregado": 2,
        "novedad": 0,
        "cancelado": 0,
    }
    assert cuenta(servicios_por_estado(DIA_19, DIA_19))["pendiente_asignar"] == 1
    assert sum(cuenta(servicios_por_estado(DIA, DIA_19)).values()) == 5


def test_el_regreso_cuenta_el_dia_de_su_fecha_de_regreso(cliente, crear_servicio):
    evento = registrada_el(
        crear_solicitud(cliente, programada_para=A_MEDIODIA, fecha_regreso=DIA_SIGUIENTE),
        A_MEDIODIA,
    )
    ida = crear_servicio(Estado.ENTREGADO, solicitud_de=evento)
    crear_servicio(solicitud_de=evento, regreso_de=ida)
    assert cuenta(servicios_por_estado(DIA, DIA)) == {
        **dict.fromkeys(cuenta(servicios_por_estado(DIA, DIA)), 0),
        "entregado": 1,
    }
    assert cuenta(servicios_por_estado(DIA_19, DIA_19))["pendiente_asignar"] == 1


def test_no_concretadas_por_motivo_del_periodo(cliente):
    for motivo, momento in [
        ("precio", A_MEDIODIA),
        ("precio", NOCHE_DEL_18),
        ("sin_grua", A_MEDIODIA),
        ("demora", DIA_SIGUIENTE),
    ]:
        registrada_el(
            crear_solicitud(
                cliente, estado_registro=EstadoRegistro.NO_CONCRETADA, motivo_no_concretada=motivo
            ),
            momento,
        )
    registrada_el(crear_solicitud(cliente), A_MEDIODIA)  # abierta: no cuenta

    assert dict(no_concretadas_por_motivo(DIA, DIA)) == {
        "Precio": 2,
        "Sin grúa disponible": 1,
        "El cliente desistió": 0,
        "Demora": 0,
        "Otro": 0,
    }
    assert sum(n for _, n in no_concretadas_por_motivo(DIA, DIA_19)) == 4


def test_por_cobrar_por_pagador_con_datos_conocidos(cliente, crear_servicio):
    aseguradora = Cliente.objects.create(nombre="Seguros Andinos", tipo=TipoCliente.ASEGURADORA)

    def linea(pagador, estado, valor=None, numero=""):
        return LineaCobro.objects.create(
            servicio=crear_servicio(Estado.ENTREGADO),
            pagador=pagador,
            posicion=1,
            estado=estado,
            valor=valor,
            numero_factura=numero,
        )

    linea(cliente, "por_facturar", Decimal(180000))
    linea(cliente, "facturado", Decimal(95000), "FE-1")
    linea(cliente, "sin_valor")
    linea(cliente, "pagado", Decimal(500000), "FE-0")
    linea(aseguradora, "facturado", Decimal(400000), "FE-2")

    filas, total = cobros_por_pagador()

    assert [(f.nombre, f.total) for f in filas] == [
        ("Seguros Andinos", Decimal(400000)),
        ("Autos del Valle", Decimal(275000)),
    ]
    valle = filas[1]
    assert (valle.sin_valor, valle.por_facturar, valle.facturadas) == (1, 1, 1)
    assert total.total == Decimal(675000)
    assert total.sin_valor == 1


def test_documentos_por_vencer_y_vencidos(grua1, grua2, ana, usuario):
    soat = TipoDocumento.objects.get(nombre="SOAT")
    hoy = dia_local()
    registrar_documento(tipo=soat, sujeto=grua1, por=usuario, vence=hoy + timedelta(days=10))
    registrar_documento(tipo=soat, sujeto=grua2, por=usuario, vence=hoy - timedelta(days=2))
    licencia = TipoDocumento.objects.get(nombre="Licencia de conducción")
    registrar_documento(tipo=licencia, sujeto=ana, por=usuario, vence=hoy + timedelta(days=300))

    documentos = datos_del_panel(hoy, hoy)["documentos"]
    # El vencido primero (vence antes); la licencia vigente no sale.
    assert [d.descripcion for d in documentos] == [
        f"SOAT de la grúa {grua2.placa}",
        f"SOAT de la grúa {grua1.placa}",
    ]


# --- Pantalla ------------------------------------------------------------------------------------


@pytest.fixture
def administrador(client, crear_usuario):
    usuario = crear_usuario("administrador")
    client.force_login(usuario)
    return usuario


def test_la_pantalla_muestra_los_totales(client, administrador, cliente, crear_servicio):
    hoy = timezone.localdate()
    LineaCobro.objects.create(
        servicio=crear_servicio(Estado.ENTREGADO),
        pagador=cliente,
        posicion=1,
        estado="por_facturar",
        valor=Decimal(180000),
    )
    crear_solicitud(
        cliente, estado_registro=EstadoRegistro.NO_CONCRETADA, motivo_no_concretada="precio"
    )

    respuesta = client.get("/dueno/")
    html = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert f"Hoy, {hoy:%d/%m/%Y}" in html
    assert "Servicios por estado" in html
    assert "No concretadas por motivo" in html
    assert "Autos del Valle" in html
    assert "$ 180.000" in html
    assert "Todos los documentos están al día." in html
    assert 'href="/dueno/"' in html  # ya está en el menú


def test_la_pantalla_acepta_un_periodo(client, administrador):
    html = client.get("/dueno/", {"desde": "2026-11-01", "hasta": "2026-11-15"}).content.decode()
    assert "Del 01/11/2026 al 15/11/2026" in html


def test_un_periodo_al_reves_se_rechaza_y_muestra_hoy(client, administrador):
    html = client.get("/dueno/", {"desde": "2026-11-15", "hasta": "2026-11-01"}).content.decode()
    assert "La fecha inicial va antes de la final." in html
    assert "Hoy," in html


@pytest.mark.parametrize("rol", ["logistica", "facturacion"])
def test_solo_el_administrador_entra(client, crear_usuario, rol):
    client.force_login(crear_usuario(rol))
    assert client.get("/dueno/").status_code == 403
