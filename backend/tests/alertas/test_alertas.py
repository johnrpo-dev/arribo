"""Alertas contra PostgreSQL: se abren una sola vez por (tipo, registro) mientras sigan abiertas,
no se borran y se resuelven guardando quién y cuándo."""
import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.utils import timezone

from alertas.models import Alerta, TipoAlerta
from alertas.operaciones import abrir_alerta, alertas_abiertas, resolver_alerta
from nucleo.estados import Estado
from solicitudes import operaciones
from solicitudes.models import Servicio

pytestmark = pytest.mark.django_db

CONFLICTO = TipoAlerta.CONFLICTO_SINCRONIZACION
CAPACIDAD = TipoAlerta.CAPACIDAD_EXCEDIDA


@pytest.fixture
def evento(crear_servicio, ana, usuario):
    return operaciones.asignar(crear_servicio(), ana, actor=usuario)


# --- Abrir ---------------------------------------------------------------------------------------


def test_abrir_alerta_la_guarda_abierta_apuntando_al_registro(evento):
    alerta = abrir_alerta(CONFLICTO, evento, "El evento no encajó.")

    alerta.refresh_from_db()
    assert alerta.abierta
    assert (alerta.tipo, alerta.mensaje) == (CONFLICTO, "El evento no encajó.")
    assert alerta.registro == evento  # un registro con llave UUID
    assert alerta.creada_en is not None
    assert (alerta.resuelta_en, alerta.resuelta_por) == (None, None)


def test_una_alerta_puede_apuntar_a_cualquier_registro(evento, ana):
    de_conductor = abrir_alerta(TipoAlerta.EVENTO_RECHAZADO, ana, "Evento sin guardar.")
    de_servicio = abrir_alerta(CAPACIDAD, evento.servicio, "Grúa llena.")

    assert Alerta.objects.get(pk=de_conductor.pk).registro == ana  # llave numérica
    assert Alerta.objects.get(pk=de_servicio.pk).registro == evento.servicio


def test_abrir_dos_veces_la_misma_alerta_deja_una_sola_y_no_cambia_el_mensaje(evento):
    primera = abrir_alerta(CONFLICTO, evento, "Primer mensaje.")
    segunda = abrir_alerta(CONFLICTO, evento, "Segundo mensaje.")

    assert segunda == primera
    assert Alerta.objects.count() == 1
    assert Alerta.objects.get().mensaje == "Primer mensaje."


def test_otro_tipo_u_otro_registro_abren_su_propia_alerta(evento, crear_servicio, ana, usuario):
    otro_evento = operaciones.asignar(crear_servicio(), ana, actor=usuario)

    abrir_alerta(CONFLICTO, evento, "a")
    abrir_alerta(CAPACIDAD, evento, "b")
    abrir_alerta(CONFLICTO, otro_evento, "c")

    assert Alerta.objects.count() == 3
    assert alertas_abiertas(evento).count() == 2
    assert alertas_abiertas(tipo=CONFLICTO).count() == 2
    assert alertas_abiertas(otro_evento, CONFLICTO).get().mensaje == "c"


def test_dos_registros_de_modelos_distintos_con_la_misma_llave_no_se_confunden(ana):
    # Un conductor y un servicio pueden tener el mismo número: el tipo de registro los separa.
    del_conductor = abrir_alerta(CAPACIDAD, ana, "del conductor")

    Alerta.objects.create(
        tipo=CAPACIDAD,
        tipo_registro=ContentType.objects.get_for_model(Servicio),
        registro_id=del_conductor.registro_id,
        mensaje="del servicio con el mismo número",
    )

    assert Alerta.objects.count() == 2
    assert alertas_abiertas(ana).get() == del_conductor


def test_un_tipo_de_alerta_desconocido_no_se_abre(evento):
    with pytest.raises(ValueError, match="inventada"):
        abrir_alerta("inventada", evento, "x")
    assert not Alerta.objects.exists()


def test_no_se_abre_una_alerta_sobre_un_registro_sin_guardar():
    with pytest.raises(ValueError, match="ya guardado"):
        abrir_alerta(CONFLICTO, Servicio(), "x")


# --- Resolver ------------------------------------------------------------------------------------


def test_resolver_guarda_quien_y_cuando_y_la_alerta_no_se_borra(evento, usuario):
    alerta = abrir_alerta(CONFLICTO, evento, "x")
    antes = timezone.now()

    resuelta = resolver_alerta(alerta, por=usuario)

    assert not resuelta.abierta
    assert resuelta.resuelta_por == usuario and resuelta.resuelta_en >= antes
    assert Alerta.objects.filter(pk=alerta.pk).exists()
    assert not alertas_abiertas(evento).exists()


def test_resolver_dos_veces_conserva_a_quien_la_resolvio_primero(
    evento, usuario, django_user_model
):
    alerta = abrir_alerta(CONFLICTO, evento, "x")
    primera = resolver_alerta(alerta, por=usuario)
    otra_persona = django_user_model.objects.create_user("otra")

    segunda = resolver_alerta(alerta, por=otra_persona)

    assert (segunda.resuelta_por, segunda.resuelta_en) == (usuario, primera.resuelta_en)


def test_despues_de_resuelta_lo_mismo_puede_volver_a_alertar(evento, usuario):
    primera = abrir_alerta(CONFLICTO, evento, "x")
    resolver_alerta(primera, por=usuario)

    segunda = abrir_alerta(CONFLICTO, evento, "otra vez")

    assert segunda != primera and segunda.abierta
    assert Alerta.objects.count() == 2
    # Y la nueva vuelve a ser única mientras siga abierta.
    assert abrir_alerta(CONFLICTO, evento, "y otra") == segunda


# --- La base manda -------------------------------------------------------------------------------


def test_la_base_no_deja_dos_alertas_abiertas_del_mismo_tipo_para_un_registro(evento):
    alerta = abrir_alerta(CONFLICTO, evento, "x")
    with (
        pytest.raises(IntegrityError, match="alerta_una_abierta_por_registro"),
        transaction.atomic(),
    ):
        Alerta.objects.create(
            tipo=CONFLICTO,
            tipo_registro=alerta.tipo_registro,
            registro_id=alerta.registro_id,
            mensaje="otra",
        )


@pytest.mark.parametrize(
    ("cambio", "restriccion"),
    [
        ({"tipo": "inventada"}, "alerta_tipo_valido"),
        ({"mensaje": ""}, "alerta_con_mensaje_y_registro"),
        ({"mensaje": "  \n "}, "alerta_con_mensaje_y_registro"),
        ({"registro_id": ""}, "alerta_con_mensaje_y_registro"),
    ],
)
def test_la_base_rechaza_una_alerta_incompleta_o_de_tipo_desconocido(evento, cambio, restriccion):
    datos = {
        "tipo": CONFLICTO,
        "tipo_registro": ContentType.objects.get_for_model(evento),
        "registro_id": str(evento.pk),
        "mensaje": "x",
        **cambio,
    }
    with pytest.raises(IntegrityError, match=restriccion), transaction.atomic():
        Alerta.objects.create(**datos)


def test_la_base_no_guarda_quien_resolvio_una_alerta_que_sigue_abierta(evento, usuario):
    alerta = abrir_alerta(CONFLICTO, evento, "x")
    with (
        pytest.raises(IntegrityError, match="alerta_resuelta_por_solo_si_resuelta"),
        transaction.atomic(),
    ):
        Alerta.objects.filter(pk=alerta.pk).update(resuelta_por=usuario)


def test_solicitudes_no_importa_alertas():
    """`solicitudes` avisa con señales; así `alertas` puede importar `solicitudes` (1a-18)."""
    import ast
    from pathlib import Path

    carpeta = Path(operaciones.__file__).parent
    for archivo in carpeta.glob("*.py"):
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            modulos = []
            if isinstance(nodo, ast.Import):
                modulos = [alias.name for alias in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                modulos = [nodo.module or ""]
            assert not any(m.split(".")[0] == "alertas" for m in modulos), archivo.name


def test_un_servicio_sin_tocar_no_tiene_alertas(crear_servicio):
    assert not alertas_abiertas(crear_servicio(Estado.ASIGNADO)).exists()
