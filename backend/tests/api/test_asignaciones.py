"""Lista y detalle de las asignaciones del conductor: qué servicios, en qué orden, con qué datos, sin
ningún valor de cobro, solo los suyos, con ETag y sin consultas de más."""
from datetime import datetime
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from api.models import TokenDispositivo
from clientes.models import Cliente, Contacto, Tarifa, TipoCliente
from cobros.models import LineaCobro
from configuracion.models import configuracion_vigente
from flota.models import AsignacionConductorGrua, Grua
from nucleo.estados import Estado
from nucleo.tipos import TipoServicio
from solicitudes import operaciones
from solicitudes.models import Servicio

from ..conftest import BOGOTA, VIN, crear_solicitud
from .conftest import URL_ASIGNACIONES, cliente_con

pytestmark = pytest.mark.django_db

E = Estado
URL = URL_ASIGNACIONES


def detalle(servicio) -> str:
    return f"{URL}{servicio.pk}/"


def ids(respuesta) -> list[int]:
    return [servicio["id"] for servicio in respuesta.json()["servicios"]]


@pytest.fixture
def porteria():
    return Contacto.objects.create(nombre="Portería Autos del Valle", telefono="604 444 5566")


@pytest.fixture
def taller():
    return Contacto.objects.create(nombre="Taller Belén", telefono="+57 310 222 3344")


@pytest.fixture
def asignado_a(nuevo_vehiculo):
    """Crea un servicio pendiente en la solicitud dada y lo asigna con la operación del panel."""

    def asignar(conductor, solicitud, **datos_servicio):
        datos_servicio.setdefault("vehiculo", nuevo_vehiculo())
        servicio = Servicio.objects.create(solicitud=solicitud, **datos_servicio)
        operaciones.asignar(servicio, conductor, actor=None)
        servicio.refresh_from_db()
        return servicio

    return asignar


# --- Qué servicios trae y en qué orden -----------------------------------------------------------


def test_sin_servicios_la_lista_viene_vacia_con_version_y_configuracion(sesion):
    respuesta = sesion.get(URL)

    assert respuesta.status_code == 200
    assert respuesta.json() == {
        "version": 1,
        "configuracion": {"minimo_fotos": 4, "momento_placa_vin": "recoger"},
        "servicios": [],
    }


def test_la_lista_trae_solo_los_servicios_no_terminales_incluida_la_novedad(
    sesion, crear_servicio
):
    activos = [crear_servicio(estado) for estado in (E.ASIGNADO, E.EN_CAMINO, E.RECOGIDO, E.NOVEDAD)]
    for terminal in (E.ENTREGADO, E.CANCELADO):
        crear_servicio(terminal)
    crear_servicio(E.PENDIENTE_ASIGNAR)

    respuesta = sesion.get(URL)

    assert sorted(ids(respuesta)) == sorted(servicio.pk for servicio in activos)
    assert {s["estado"] for s in respuesta.json()["servicios"]} == {
        "asignado", "en_camino", "recogido", "novedad"
    }


@pytest.mark.parametrize(
    ("estado", "previo", "montado"),
    [
        (E.ASIGNADO, None, False),
        (E.EN_CAMINO, None, False),
        (E.RECOGIDO, None, True),
        (E.NOVEDAD, E.ASIGNADO, False),
        (E.NOVEDAD, E.EN_CAMINO, False),
        (E.NOVEDAD, E.RECOGIDO, True),
    ],
)
def test_la_novedad_trae_su_estado_previo_y_a_bordo_sigue_la_regla_del_nucleo(
    sesion, crear_servicio, estado, previo, montado
):
    crear_servicio(estado, previo=previo)

    (servicio,) = sesion.get(URL).json()["servicios"]

    assert servicio["estado"] == estado.value
    assert servicio["estado_previo"] == (previo.value if previo else None)
    assert servicio["a_bordo"] is montado


def test_la_lista_va_en_el_orden_de_la_ronda(sesion, ana_app, solicitud, asignado_a):
    primero, segundo, tercero = (asignado_a(ana_app, solicitud) for _ in range(3))
    operaciones.mover_en_ronda(tercero, "subir")

    servicios = sesion.get(URL).json()["servicios"]

    assert [s["id"] for s in servicios] == [primero.pk, tercero.pk, segundo.pk]
    assert [s["orden_ronda"] for s in servicios] == [1, 2, 3]


# --- Qué datos trae cada servicio ----------------------------------------------------------------


def test_cada_servicio_trae_lo_que_la_app_necesita_para_trabajar_sin_senal(
    sesion, ana_app, grua1, cliente, porteria, taller, nuevo_vehiculo, asignado_a
):
    solicitud = crear_solicitud(
        cliente,
        origen_ubicacion="https://maps.app.goo.gl/origen",
        contacto_origen=porteria,
        contacto_destino=taller,
        programada_para=datetime(2026, 11, 20, 14, 30, tzinfo=BOGOTA),
    )
    vehiculo = nuevo_vehiculo(placa="ABC123", vin=VIN, marca="Mazda", linea="CX-30", color="Rojo")
    servicio = asignado_a(ana_app, solicitud, vehiculo=vehiculo, referencia_externa="SIN-4471")

    assert sesion.get(URL).json()["servicios"] == [
        {
            "id": servicio.pk,
            "solicitud_id": solicitud.pk,
            "estado": "asignado",
            "estado_previo": None,
            "tipo": "traslado",
            "es_regreso": False,
            "orden_ronda": 1,
            "vehiculo": {
                "placa": "ABC123",
                "vin": VIN,
                "marca": "Mazda",
                "linea": "CX-30",
                "color": "Rojo",
            },
            "origen": {
                "direccion": "Calle 10 # 43-20, El Poblado",
                "ubicacion": "https://maps.app.goo.gl/origen",
                "contacto": {"nombre": "Portería Autos del Valle", "telefono": "6044445566"},
            },
            "destino": {
                "direccion": "Carrera 70 # 1-50, Belén",
                "ubicacion": None,
                "contacto": {"nombre": "Taller Belén", "telefono": "3102223344"},
            },
            "referencia_externa": "SIN-4471",
            "programada_para": "2026-11-20T19:30:00Z",
            "grua": {"id": grua1.pk, "placa": "GRU001", "capacidad": 1},
            "a_bordo": False,
        }
    ]


def test_los_datos_que_faltan_van_como_null_y_sin_hora_es_inmediato(
    sesion, ana_app, cliente, nuevo_vehiculo, asignado_a
):
    desvare = crear_solicitud(cliente, tipo=TipoServicio.DESVARE, destino="")
    asignado_a(ana_app, desvare, vehiculo=nuevo_vehiculo(placa="XYZ789"))

    (servicio,) = sesion.get(URL).json()["servicios"]

    assert servicio["tipo"] == "desvare"
    assert servicio["destino"] == {"direccion": None, "ubicacion": None, "contacto": None}
    assert servicio["origen"]["contacto"] is None
    assert servicio["programada_para"] is None
    assert servicio["referencia_externa"] is None
    assert servicio["vehiculo"] == {
        "placa": "XYZ789", "vin": None, "marca": None, "linea": None, "color": None
    }


def test_el_regreso_va_del_destino_al_origen_y_en_la_fecha_de_regreso(
    sesion, ana_app, cliente, porteria, taller, nuevo_vehiculo, asignado_a
):
    evento = crear_solicitud(
        cliente,
        tipo=TipoServicio.EVENTO,
        contacto_origen=porteria,
        contacto_destino=taller,
        programada_para=datetime(2026, 11, 20, 8, 0, tzinfo=BOGOTA),
        tiene_regreso=True,
        fecha_regreso=datetime(2026, 11, 22, 17, 0, tzinfo=BOGOTA),
    )
    vehiculo = nuevo_vehiculo()
    ida = asignado_a(ana_app, evento, vehiculo=vehiculo)
    regreso = asignado_a(ana_app, evento, vehiculo=vehiculo, regreso_de=ida)

    servicios = {s["id"]: s for s in sesion.get(URL).json()["servicios"]}
    de_ida, de_regreso = servicios[ida.pk], servicios[regreso.pk]

    assert (de_ida["es_regreso"], de_regreso["es_regreso"]) == (False, True)
    assert de_ida["origen"]["direccion"] == "Calle 10 # 43-20, El Poblado"
    assert de_regreso["origen"] == de_ida["destino"]
    assert de_regreso["destino"] == de_ida["origen"]
    assert de_regreso["origen"]["contacto"]["nombre"] == "Taller Belén"
    assert de_ida["programada_para"] == "2026-11-20T13:00:00Z"
    assert de_regreso["programada_para"] == "2026-11-22T22:00:00Z"


def test_la_grua_es_la_guardada_en_el_servicio_aunque_el_conductor_cambie_de_grua(
    sesion, ana_app, grua1, solicitud, asignado_a
):
    asignado_a(ana_app, solicitud)
    ahora = timezone.now()
    AsignacionConductorGrua.objects.filter(conductor=ana_app).update(fin=ahora)
    AsignacionConductorGrua.objects.create(
        conductor=ana_app, grua=Grua.objects.create(placa="GRU009", capacidad=2), inicio=ahora
    )

    (servicio,) = sesion.get(URL).json()["servicios"]

    assert servicio["grua"] == {"id": grua1.pk, "placa": "GRU001", "capacidad": 1}


def test_la_lista_trae_la_configuracion_vigente(sesion):
    configuracion = configuracion_vigente()
    configuracion.minimo_fotos = 6
    configuracion.momento_placa_vin = "asignar"
    configuracion.save()

    assert sesion.get(URL).json()["configuracion"] == {
        "minimo_fotos": 6,
        "momento_placa_vin": "asignar",
    }


# --- Nunca valores de cobro ----------------------------------------------------------------------

FRAGMENTOS_DE_COBRO = ("valor", "tarifa", "cobro", "factura", "pagador", "precio")


def _claves(dato):
    """Todas las claves del JSON, a cualquier profundidad."""
    if isinstance(dato, dict):
        for clave, valor in dato.items():
            yield clave
            yield from _claves(valor)
    elif isinstance(dato, list):
        for elemento in dato:
            yield from _claves(elemento)


def test_el_recorrido_de_claves_encuentra_una_clave_anidada():
    assert "valor" in set(_claves({"servicios": [{"grua": {"valor": 1}}]}))


def test_la_respuesta_no_contiene_ningun_valor_de_cobro(
    sesion, ana_app, cliente, crear_servicio, asignado_a
):
    pagador = Cliente.objects.create(
        nombre="Aseguradora Pagadora Única", tipo=TipoCliente.ASEGURADORA
    )
    solicitud = crear_solicitud(cliente, pagador=pagador)
    Tarifa.objects.create(
        cliente=pagador, tipo_servicio=TipoServicio.TRASLADO, valor=Decimal("876543.21")
    )
    activo = asignado_a(ana_app, solicitud, referencia_externa="CASO-1")
    LineaCobro.objects.create(
        servicio=activo, pagador=pagador, estado="por_facturar", valor=Decimal("987654.32")
    )
    entregado = crear_servicio(E.ENTREGADO, solicitud_de=solicitud)
    LineaCobro.objects.create(
        servicio=entregado,
        pagador=pagador,
        estado="facturado",
        valor=Decimal("765432.10"),
        numero_factura="FE-24680",
    )

    for url in (URL, detalle(activo)):
        respuesta = sesion.get(url)
        assert respuesta.status_code == 200
        claves = set(_claves(respuesta.json()))
        assert not {c for c in claves if any(f in c.lower() for f in FRAGMENTOS_DE_COBRO)}
        texto = respuesta.content.decode()
        for prohibido in ("987654", "876543", "765432", "FE-24680", "Aseguradora Pagadora"):
            assert prohibido not in texto


# --- Solo los suyos ------------------------------------------------------------------------------

NO_ENCONTRADO = {
    "version": 1,
    "error": "no_encontrado",
    "detalle": "El servicio no existe o ya no está asignado a usted.",
}


def test_un_conductor_no_ve_en_su_lista_los_servicios_de_otro(sesion, beto_app, crear_servicio):
    de_ana = crear_servicio(E.ASIGNADO)
    crear_servicio(E.ASIGNADO, conductor=beto_app)
    crear_servicio(E.NOVEDAD, conductor=beto_app)

    assert ids(sesion.get(URL)) == [de_ana.pk]


def test_el_detalle_de_un_servicio_ajeno_responde_404_igual_que_uno_inexistente(
    sesion, beto_app, crear_servicio
):
    de_beto = crear_servicio(E.EN_CAMINO, conductor=beto_app)

    ajeno = sesion.get(detalle(de_beto))
    inexistente = sesion.get(f"{URL}999999/")

    assert ajeno.status_code == inexistente.status_code == 404
    assert ajeno.json() == NO_ENCONTRADO
    assert ajeno.content == inexistente.content


def test_el_detalle_de_un_servicio_propio_ya_terminado_responde_404(sesion, crear_servicio):
    entregado = crear_servicio(E.ENTREGADO)

    assert sesion.get(detalle(entregado)).json() == NO_ENCONTRADO


def test_el_detalle_trae_el_mismo_servicio_que_la_lista(sesion, crear_servicio):
    servicio = crear_servicio(E.EN_CAMINO)

    lista = sesion.get(URL).json()
    uno = sesion.get(detalle(servicio))

    assert uno.status_code == 200
    assert uno.json() == {
        "version": 1,
        "configuracion": lista["configuracion"],
        "servicio": lista["servicios"][0],
    }


def test_un_servicio_reasignado_pasa_de_la_lista_de_un_conductor_a_la_del_otro(
    sesion, ana_app, beto_app, solicitud, asignado_a
):
    servicio = asignado_a(ana_app, solicitud)
    operaciones.reasignar(servicio, beto_app, actor=None)
    _, clave_de_beto = TokenDispositivo.emitir(beto_app, "celular-de-beto")

    assert ids(sesion.get(URL)) == []
    assert sesion.get(detalle(servicio)).status_code == 404
    assert ids(cliente_con(clave_de_beto).get(URL)) == [servicio.pk]


# --- Refrescos baratos: ETag ---------------------------------------------------------------------


def test_la_lista_trae_etag_y_responde_304_sin_cuerpo_si_nada_cambio(sesion, crear_servicio):
    crear_servicio(E.ASIGNADO)
    primera = sesion.get(URL)
    etag = primera["ETag"]

    segunda = sesion.get(URL, HTTP_IF_NONE_MATCH=etag)

    assert segunda.status_code == 304
    assert segunda.content == b""
    assert segunda["ETag"] == etag
    assert primera["Cache-Control"] == "private, no-cache"


def test_un_etag_marcado_como_debil_tambien_vale(sesion, crear_servicio):
    crear_servicio(E.ASIGNADO)
    etag = sesion.get(URL)["ETag"]

    assert sesion.get(URL, HTTP_IF_NONE_MATCH=f"W/{etag}").status_code == 304


def test_el_etag_cambia_si_cambia_la_ronda_aunque_no_haya_evento(
    sesion, ana_app, solicitud, asignado_a
):
    asignado_a(ana_app, solicitud)
    segundo = asignado_a(ana_app, solicitud)
    etag = sesion.get(URL)["ETag"]

    operaciones.mover_en_ronda(segundo, "subir")
    respuesta = sesion.get(URL, HTTP_IF_NONE_MATCH=etag)

    assert respuesta.status_code == 200
    assert respuesta["ETag"] != etag
    assert ids(respuesta)[0] == segundo.pk


def test_el_etag_cambia_si_cambia_el_estado_o_la_configuracion(sesion, crear_servicio):
    servicio = crear_servicio(E.ASIGNADO)
    etag = sesion.get(URL)["ETag"]

    operaciones.cambiar_estado(servicio, E.NOVEDAD, actor=None, motivo="Llanta pinchada")
    tras_novedad = sesion.get(URL, HTTP_IF_NONE_MATCH=etag)
    assert tras_novedad.status_code == 200

    configuracion = configuracion_vigente()
    configuracion.minimo_fotos = 2
    configuracion.save()
    tras_configuracion = sesion.get(URL, HTTP_IF_NONE_MATCH=tras_novedad["ETag"])
    assert tras_configuracion.status_code == 200


def test_el_detalle_tambien_responde_304_si_nada_cambio(sesion, crear_servicio):
    servicio = crear_servicio(E.RECOGIDO)
    etag = sesion.get(detalle(servicio))["ETag"]

    assert sesion.get(detalle(servicio), HTTP_IF_NONE_MATCH=etag).status_code == 304


# --- Consultas -----------------------------------------------------------------------------------


def test_la_lista_hace_las_mismas_pocas_consultas_con_2_o_con_8_servicios(
    sesion, ana_app, cliente, porteria, taller, nuevo_vehiculo, asignado_a,
    django_assert_max_num_queries,
):
    configuracion_vigente()  # que la consulta no cuente la creación de la configuración

    def agregar(cuantos):
        for _ in range(cuantos):
            evento = crear_solicitud(
                cliente,
                tipo=TipoServicio.EVENTO,
                contacto_origen=porteria,
                contacto_destino=taller,
                tiene_regreso=True,
                fecha_regreso=datetime(2026, 11, 22, 17, 0, tzinfo=BOGOTA),
            )
            vehiculo = nuevo_vehiculo(marca="Kia")
            ida = asignado_a(ana_app, evento, vehiculo=vehiculo)
            asignado_a(ana_app, evento, vehiculo=vehiculo, regreso_de=ida)

    agregar(1)
    with CaptureQueriesContext(connection) as con_pocos:
        assert len(sesion.get(URL).json()["servicios"]) == 2

    agregar(3)
    with django_assert_max_num_queries(len(con_pocos)):
        assert len(sesion.get(URL).json()["servicios"]) == 8

    # Token (con su grupo), último uso, configuración y servicios.
    assert len(con_pocos) <= 4
