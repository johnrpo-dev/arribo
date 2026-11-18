"""Datos de demostración (1a-20) contra PostgreSQL: `demo_cargar` deja una operación completa
marcada como demo y `demo_borrar` la quita sin tocar un solo registro real."""
from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.apps import apps
from django.core.management import CommandError, call_command
from django.utils import timezone

from alertas.evaluacion import evaluar
from alertas.models import Alerta, TipoAlerta
from alertas.operaciones import abrir_alerta
from clientes.models import Cliente, Tarifa
from cobros import operaciones as cobros
from cobros.models import LineaCobro
from documentos.models import Documento, TipoDocumento
from documentos.operaciones import registrar_documento
from flota.models import Conductor, Grua
from nucleo.estados import Estado
from panel import demo
from solicitudes import operaciones
from solicitudes.models import EstadoRegistro, EventoEstado, Servicio, Solicitud, Vehiculo
from tests.conftest import crear_solicitud

pytestmark = pytest.mark.django_db

APPS_PROPIAS = ("flota", "clientes", "solicitudes", "cobros", "documentos", "alertas",
                "configuracion", "api", "auth")


def foto_de_la_base() -> dict:
    """Cada fila de cada tabla propia (y de usuarios y grupos), con todos sus valores."""
    foto = {}
    for modelo in apps.get_models(include_auto_created=True):
        if modelo._meta.app_label in APPS_PROPIAS:
            foto[modelo._meta.label] = list(modelo.objects.order_by("pk").values())
    return foto


@pytest.fixture
def datos_reales(cliente, ana, grua1, usuario, nuevo_vehiculo):
    """Una operación real pequeña: una solicitud con un servicio entregado (eventos, línea de
    cobro facturada con historial), uno pendiente, un documento y una alerta abierta."""
    solicitud = crear_solicitud(cliente)
    servicio = Servicio.objects.create(solicitud=solicitud, vehiculo=nuevo_vehiculo())
    operaciones.asignar(servicio, ana, actor=usuario)
    for destino in (Estado.EN_CAMINO, Estado.RECOGIDO, Estado.ENTREGADO):
        operaciones.cambiar_estado(servicio, destino, actor=usuario, nombre_quien="Portería")
    linea = LineaCobro.objects.get(servicio=servicio)
    cobros.fijar_valor(linea, Decimal(120000), actor=usuario)
    cobros.facturar(linea, "FE-77", actor=usuario)
    pendiente = Servicio.objects.create(solicitud=solicitud, vehiculo=nuevo_vehiculo())
    Tarifa.objects.create(cliente=cliente, tipo_servicio="traslado", valor=Decimal(90000))
    registrar_documento(
        tipo=TipoDocumento.objects.get(nombre="SOAT"), sujeto=grua1,
        por=usuario, vence=timezone.localdate() + timedelta(days=3),
    )
    abrir_alerta(TipoAlerta.CONFLICTO_SINCRONIZACION, pendiente, "Alerta real de prueba.")
    evaluar()  # lo que el temporizador ya habría hecho con los datos reales
    return solicitud


def test_cargar_deja_todos_los_estados_marcados_como_demo():
    resumen = demo.cargar()

    gruas = Grua.objects.filter(es_demo=True)
    assert gruas.count() == 3
    assert Conductor.objects.filter(es_demo=True).count() == 3
    assert all(c.usuario_id for c in Conductor.objects.filter(es_demo=True))
    clientes = Cliente.objects.filter(es_demo=True)
    assert clientes.count() == 3
    assert Tarifa.objects.filter(cliente__in=clientes).count() == 1
    assert all(c.nombre.endswith("(demo)") for c in clientes)

    servicios = Servicio.objects.filter(solicitud__es_demo=True)
    assert set(servicios.values_list("estado", flat=True)) == {e.value for e in Estado}
    assert not Servicio.objects.filter(solicitud__es_demo=False).exists()
    assert not Vehiculo.objects.filter(es_demo=False).exists()
    registros = set(Solicitud.objects.filter(es_demo=True).values_list("estado_registro",
                                                                        flat=True))
    assert registros == set(EstadoRegistro.values)
    assert set(LineaCobro.objects.filter(servicio__in=servicios).values_list(
        "estado", flat=True)) == {"sin_valor", "por_facturar", "facturado", "pagado"}
    assert EventoEstado.objects.filter(servicio__in=servicios).exists()

    abiertas = set(Alerta.objects.filter(resuelta_en__isnull=True).values_list("tipo", flat=True))
    assert {
        TipoAlerta.SIN_ASIGNAR, TipoAlerta.RECOGIDO_SIN_ENTREGADO,
        TipoAlerta.DOCUMENTO_POR_VENCER, TipoAlerta.CONFLICTO_SINCRONIZACION,
    } <= abiertas
    documentos = Documento.objects.filter(es_demo=True)
    hoy = timezone.localdate()
    assert documentos.filter(vence__lt=hoy).count() == 1  # vencido
    assert documentos.filter(vence__gte=hoy, vence__lte=hoy + timedelta(days=60)).count() == 1
    assert resumen.cuentas["grúas"] == 3
    assert resumen.cuentas["alertas abiertas"] >= 4


def test_borrar_deja_intactos_los_registros_reales(datos_reales):
    antes = foto_de_la_base()

    demo.cargar()
    assert foto_de_la_base() != antes
    demo.borrar()

    assert foto_de_la_base() == antes
    assert not demo.hay_demo()


def test_borrar_quita_todo_lo_que_cuelga_de_la_demo():
    demo.cargar()
    usuarios = list(Conductor.objects.filter(es_demo=True).values_list("usuario_id", flat=True))

    demo.borrar()

    assert not Servicio.objects.exists()
    assert not EventoEstado.objects.exists()
    assert not LineaCobro.objects.exists()
    assert not Alerta.objects.exists()
    assert not Documento.objects.exists()
    assert not Grua.objects.exists()
    assert not Cliente.objects.exists()
    assert not apps.get_model("auth.User").objects.filter(pk__in=usuarios).exists()
    assert all(n == 0 for n in demo.contar().cuentas.values())


def test_se_puede_cargar_otra_vez_despues_de_borrar():
    demo.cargar()
    demo.borrar()
    assert demo.cargar().cuentas["servicios"] == Servicio.objects.count()


def test_no_se_carga_dos_veces():
    demo.cargar()
    with pytest.raises(demo.DemoYaCargada):
        demo.cargar()


def test_no_carga_nada_si_choca_con_un_dato_real():
    Grua.objects.create(placa="DEMO02", capacidad=1)
    with pytest.raises(demo.DemoEnConflicto, match="DEMO02"):
        demo.cargar()
    assert not demo.hay_demo()
    assert Grua.objects.count() == 1


def test_no_borra_nada_si_un_dato_real_usa_la_demo():
    demo.cargar()
    concesionario = Cliente.objects.get(es_demo=True, tipo="concesionario")
    real = crear_solicitud(concesionario)  # una solicitud real a nombre del cliente de demo
    antes = foto_de_la_base()

    with pytest.raises(demo.DemoEnConflicto, match="No se borró nada"):
        demo.borrar()

    assert foto_de_la_base() == antes
    assert Solicitud.objects.filter(pk=real.pk, es_demo=False).exists()


def test_no_borra_nada_si_un_servicio_real_es_de_un_conductor_de_demo(cliente, usuario):
    demo.cargar()
    esteban = Conductor.objects.filter(es_demo=True).order_by("pk")[2]  # sin documento vencido
    servicio = Servicio.objects.create(
        solicitud=crear_solicitud(cliente), vehiculo=Vehiculo.objects.create(placa="REA123")
    )
    operaciones.asignar(servicio, esteban, actor=usuario)
    antes = foto_de_la_base()

    with pytest.raises(demo.DemoEnConflicto):
        demo.borrar()

    assert foto_de_la_base() == antes


# --- Comandos ------------------------------------------------------------------------------------


def test_los_comandos_cargan_y_borran():
    salida = StringIO()
    call_command("demo_cargar", stdout=salida)
    assert "Demo cargada: 3 grúas, 3 conductores, 3 clientes" in salida.getvalue()

    salida = StringIO()
    call_command("demo_borrar", "--noinput", stdout=salida)
    assert "Demo borrada" in salida.getvalue()
    assert not demo.hay_demo()


def test_demo_borrar_sin_demo_no_hace_nada():
    salida = StringIO()
    call_command("demo_borrar", "--noinput", stdout=salida)
    assert "No hay datos de demo" in salida.getvalue()


def test_demo_borrar_pide_confirmacion(monkeypatch):
    demo.cargar()
    monkeypatch.setattr("builtins.input", lambda _texto: "no")
    salida = StringIO()
    call_command("demo_borrar", stdout=salida)
    assert "Cancelado" in salida.getvalue()
    assert demo.hay_demo()


def test_demo_cargar_dos_veces_es_un_error_claro():
    call_command("demo_cargar", stdout=StringIO())
    with pytest.raises(CommandError, match="demo_borrar"):
        call_command("demo_cargar", stdout=StringIO())
