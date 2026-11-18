"""Datos ficticios de demostración (1a-20): `manage.py demo_cargar` y `manage.py demo_borrar`.

La demo se carga con las operaciones reales (asignar, eventos de la app del conductor, cobros,
documentos), así deja eventos, historial, líneas de cobro y alertas como los dejaría el uso real.
Todo lo que tiene la marca `es_demo` (grúas, conductores, clientes, vehículos, solicitudes y
documentos) es de la demo; lo que cuelga de ellos (servicios, eventos, cobros, alertas, teléfonos,
contactos, tarifas, asignaciones, el usuario de cada conductor) se reconoce por esa raíz.

`borrar()` quita solo eso, de los hijos a los padres, en una transacción: o se borra toda la demo o
nada. Si algún dato real quedó usando un dato de la demo (por ejemplo, una solicitud real con un
cliente de la demo), no borra nada y dice qué lo impide. Es la única excepción a "nada se borra":
los eventos y el historial de cobro son de solo agregar, pero los de la demo nunca fueron reales.
Vive en `panel` porque, como el panel del dueño, junta todos los dominios.
"""
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.storage import default_storage
from django.db import IntegrityError, connection, models, transaction
from django.db.models import ProtectedError, Q
from django.utils import timezone

from alertas.evaluacion import evaluar
from alertas.models import Alerta
from api.models import NotificacionPush, TokenDispositivo
from clientes.models import Cliente, Contacto, Tarifa, TelefonoCliente, TipoCliente
from cobros import operaciones as cobros
from cobros.models import HistorialCobro, LineaCobro, LineaEnRelacion, RelacionCobro
from configuracion.models import configuracion_vigente
from documentos.models import Documento, TipoDocumento
from documentos.operaciones import registrar_documento
from flota.models import AsignacionConductorGrua, Conductor, Grua
from flota.operaciones import crear_conductor
from nucleo.estados import Estado
from nucleo.tipos import TipoServicio
from solicitudes import operaciones
from solicitudes.models import (
    EstadoRegistro,
    EventoEstado,
    Evidencia,
    MotivoNoConcretada,
    Servicio,
    Solicitud,
    Vehiculo,
)

Usuario = get_user_model()

MARCA = " (demo)"  # va en el nombre de clientes y conductores: se ven distintos en el panel

GRUAS = (("DEMO01", 1, "Grúa de planchón (demo)"), ("DEMO02", 2, "Grúa doble (demo)"),
         ("DEMO03", 2, "Grúa doble (demo)"))
CONDUCTORES = (("Carlos Ríos", "3009990001"), ("Diana Mejía", "3009990002"),
               ("Esteban Ruiz", "3009990003"))
TELEFONOS_CLIENTES = ("6049990001", "3009990101", "3009990102")
VALOR_TARIFA = Decimal(180000)


class DemoYaCargada(Exception):
    """Ya hay datos de demo: se borran antes de volver a cargar."""


class DemoEnConflicto(Exception):
    """Un dato real usa la misma placa o celular que la demo, o un dato real usa la demo."""


@dataclass
class Resumen:
    cuentas: dict[str, int] = field(default_factory=dict)

    def __str__(self):
        return ", ".join(f"{n} {nombre}" for nombre, n in self.cuentas.items())


# --- Cargar ------------------------------------------------------------------------------------


def hay_demo() -> bool:
    return any(
        modelo.objects.filter(es_demo=True).exists()
        for modelo in (Grua, Conductor, Cliente, Vehiculo, Solicitud, Documento)
    )


def _verificar_que_no_choca(placas: list[str]) -> None:
    choques = []
    gruas = [placa for placa, _, _ in GRUAS]
    choques += [f"la grúa {p}" for p in Grua.objects.filter(placa__in=gruas).values_list(
        "placa", flat=True)]
    celulares = [c for _, c in CONDUCTORES]
    choques += [f"el conductor con celular {c}" for c in Conductor.objects.filter(
        celular__in=celulares).values_list("celular", flat=True)]
    choques += [f"el vehículo {p}" for p in Vehiculo.objects.filter(placa__in=placas).values_list(
        "placa", flat=True)]
    choques += [f"el teléfono {t}" for t in TelefonoCliente.objects.filter(
        numero__in=TELEFONOS_CLIENTES).values_list("numero", flat=True)]
    if choques:
        raise DemoEnConflicto(
            "La demo usa datos que ya existen y no son de la demo: " + "; ".join(choques) + "."
        )


class _Cargador:
    """Arma la demo paso a paso. Las horas son relativas a `ahora` para que las alertas por umbral
    (sin asignar, Recogido sin Entregado, documento por vencer) se cumplan al cargar."""

    def __init__(self, ahora):
        self.ahora = ahora
        self.configuracion = configuracion_vigente()
        self.secuencias: dict[int, int] = {}
        self.placas = iter(f"DMO{n:03d}" for n in range(101, 200))

    # Catálogos ---------------------------------------------------------------------------------

    def flota(self):
        self.gruas = []
        for placa, capacidad, descripcion in GRUAS:
            self.gruas.append(Grua.objects.create(
                placa=placa, capacidad=capacidad, descripcion=descripcion, es_demo=True
            ))
        self.conductores = []
        for (nombre, celular), grua in zip(CONDUCTORES, self.gruas, strict=True):
            # PIN al azar y no se muestra: para probar la app, el dueño le pone uno desde Flota.
            pin = f"{secrets.randbelow(10**6):06d}"
            conductor = crear_conductor(nombre=nombre + MARCA, celular=celular, pin=pin, grua=grua)
            Conductor.objects.filter(pk=conductor.pk).update(es_demo=True)
            conductor.refresh_from_db()
            self.conductores.append(conductor)

    def clientes(self):
        self.concesionario = Cliente.objects.create(
            nombre="Concesionario Los Andes" + MARCA, tipo=TipoCliente.CONCESIONARIO,
            documento="900000001", es_demo=True,
        )
        Tarifa.objects.create(
            cliente=self.concesionario, tipo_servicio=TipoServicio.TRASLADO.value,
            valor=VALOR_TARIFA, descripcion="Convenio de traslados en el Valle de Aburrá (demo)",
        )
        self.aseguradora = Cliente.objects.create(
            nombre="Asistencia Vial Andina" + MARCA, tipo=TipoCliente.ASEGURADORA,
            documento="900000002", es_demo=True,
        )
        self.particular = Cliente.objects.create(
            nombre="Laura Gómez" + MARCA, tipo=TipoCliente.PARTICULAR, es_demo=True
        )
        for cliente, numero in zip(
            (self.concesionario, self.aseguradora, self.particular), TELEFONOS_CLIENTES, strict=True
        ):
            TelefonoCliente.objects.create(cliente=cliente, numero=numero)
        self.contacto = Contacto.objects.create(
            nombre="Jorge, patio del concesionario" + MARCA, telefono="3009990201",
            cliente=self.concesionario,
        )

    # Solicitudes y servicios -------------------------------------------------------------------

    def solicitud(self, cliente, tipo=TipoServicio.TRASLADO, *, hace=None, **otros):
        datos = {
            "solicitante": cliente,
            "tipo": tipo.value,
            "origen": "Calle 10 # 43-20, El Poblado",
            "destino": "Carrera 70 # 1-50, Belén",
            "estado_registro": EstadoRegistro.ABIERTA,
            "es_demo": True,
        }
        if cliente == self.concesionario:
            datos["contacto_origen"] = self.contacto
        datos.update(otros)
        solicitud = Solicitud.objects.create(**datos)
        if hace is not None:  # creada_en se llena sola: se corre al pasado después
            Solicitud.objects.filter(pk=solicitud.pk).update(creada_en=self.ahora - hace)
            solicitud.refresh_from_db()
        return solicitud

    def servicio(self, solicitud, *, marca="Renault", linea="Logan"):
        vehiculo = Vehiculo.objects.create(
            placa=next(self.placas), marca=marca, linea=linea, es_demo=True
        )
        return Servicio.objects.create(solicitud=solicitud, vehiculo=vehiculo)

    def asignar(self, servicio, conductor):
        operaciones.asignar(servicio, conductor, actor=None)

    def toque(self, servicio, destino, *, hace, **otros):
        """Un toque del conductor en la app, con la hora del celular en el pasado."""
        conductor = servicio.conductor
        self.secuencias[conductor.pk] = self.secuencias.get(conductor.pk, 0) + 1
        operaciones.aplicar_evento_del_conductor(
            id=uuid.uuid4(), servicio=servicio, conductor=conductor, destino=destino,
            secuencia=self.secuencias[conductor.pk], hora_dispositivo=self.ahora - hace, **otros
        )
        servicio.refresh_from_db()

    def entregar(self, servicio, conductor, *, hace):
        self.asignar(servicio, conductor)
        self.toque(servicio, Estado.EN_CAMINO, hace=hace + timedelta(minutes=70))
        self.toque(servicio, Estado.RECOGIDO, hace=hace + timedelta(minutes=40))
        self.toque(servicio, Estado.ENTREGADO, hace=hace, nombre_quien="Recibe en portería")
        return LineaCobro.objects.get(servicio=servicio)

    def servicios(self):
        carlos, diana, esteban = self.conductores
        hora = timedelta(hours=1)

        # Entregados de hoy, con su línea de cobro en cada estado (Esteban, uno tras otro).
        con_tarifa = self.solicitud(self.concesionario, hace=8 * hora)
        # Nace por facturar con la tarifa del concesionario.
        self.entregar(self.servicio(con_tarifa), esteban, hace=6 * hora)
        facturada = self.entregar(
            self.servicio(con_tarifa, marca="Kia", linea="Picanto"), esteban, hace=5 * hora
        )
        cobros.facturar(facturada, "DEMO-0001", actor=None)
        pagada = self.entregar(
            self.servicio(con_tarifa, marca="Mazda", linea="2"), esteban, hace=4 * hora
        )
        cobros.facturar(pagada, "DEMO-0002", actor=None)
        cobros.pagar(pagada, actor=None)
        particular = self.solicitud(self.particular, TipoServicio.DESVARE, hace=7 * hora)
        self.entregar(self.servicio(particular, marca="Chevrolet", linea="Spark"), esteban,
                      hace=3 * hora)  # sin tarifa: queda sin valor
        aseguradora = self.solicitud(self.aseguradora, TipoServicio.DESVARE, hace=6 * hora)
        con_valor = self.entregar(self.servicio(aseguradora, marca="Toyota", linea="Hilux"),
                                  esteban, hace=2 * hora)
        cobros.fijar_valor(con_valor, Decimal(250000), actor=None)

        # Asignado (Esteban) y en novedad (Esteban, el cliente no contesta).
        self.asignar(self.servicio(self.solicitud(self.concesionario, hace=hora)), esteban)
        novedad = self.servicio(self.solicitud(self.particular, hace=2 * hora), marca="Ford",
                                linea="Fiesta")
        self.asignar(novedad, esteban)
        self.toque(novedad, Estado.EN_CAMINO, hace=90 * timedelta(minutes=1))
        self.toque(novedad, Estado.NOVEDAD, hace=timedelta(minutes=50),
                   motivo="El cliente no contesta y el portero no deja entrar.")

        # Diana: uno en camino y uno Recogido hace más del umbral (alerta).
        en_camino = self.servicio(self.solicitud(self.aseguradora, TipoServicio.DESVARE,
                                                 hace=hora))
        self.asignar(en_camino, diana)
        self.toque(en_camino, Estado.EN_CAMINO, hace=timedelta(minutes=20))
        demorado = self.servicio(self.solicitud(self.concesionario, hace=8 * hora),
                                 marca="Hyundai", linea="Tucson")
        horas = self.configuracion.alerta_recogido_sin_entregado_horas
        self.asignar(demorado, diana)
        self.toque(demorado, Estado.EN_CAMINO, hace=(horas + 2) * hora)
        self.toque(demorado, Estado.RECOGIDO, hace=(horas + 1) * hora)

        # Carlos: uno recogido hace poco.
        recogido = self.servicio(self.solicitud(self.concesionario, hace=2 * hora),
                                 marca="Nissan", linea="March")
        self.asignar(recogido, carlos)
        self.toque(recogido, Estado.EN_CAMINO, hace=hora)
        self.toque(recogido, Estado.RECOGIDO, hace=timedelta(minutes=30))

        # Cancelado, y el conductor que lo marca En camino sin saber: conflicto (alerta).
        cancelado = self.servicio(self.solicitud(self.particular, hace=3 * hora),
                                  marca="Suzuki", linea="Swift")
        self.asignar(cancelado, carlos)
        operaciones.cambiar_estado(cancelado, Estado.CANCELADO, actor=None,
                                   motivo="El cliente consiguió quién lo llevara.")
        cancelado.refresh_from_db()
        self.toque(cancelado, Estado.EN_CAMINO, hace=timedelta(minutes=10))

        # Pendientes: uno inmediato que ya pasó el umbral (alerta), uno programado para mañana y
        # un evento de concesionario con regreso.
        minutos = self.configuracion.alerta_sin_asignar_minutos
        self.servicio(self.solicitud(self.particular, TipoServicio.DESVARE,
                                     hace=timedelta(minutes=minutos + 25)),
                      marca="Volkswagen", linea="Gol")
        manana = timezone.localtime(self.ahora).replace(hour=9, minute=0, second=0,
                                                        microsecond=0) + timedelta(days=1)
        self.servicio(self.solicitud(self.concesionario, programada_para=manana))
        evento = self.solicitud(
            self.concesionario, TipoServicio.EVENTO, programada_para=manana,
            tiene_regreso=True, fecha_regreso=manana + timedelta(days=2, hours=8),
            destino="Centro comercial Santafé, Medellín",
        )
        ida = self.servicio(evento, marca="Renault", linea="Duster")
        Servicio.objects.create(solicitud=evento, vehiculo=ida.vehiculo, regreso_de=ida)

        # Un borrador sin destino y una llamada no concretada por precio.
        self.solicitud(self.particular, estado_registro=EstadoRegistro.BORRADOR, destino="",
                       hace=timedelta(minutes=15))
        self.solicitud(self.aseguradora, estado_registro=EstadoRegistro.NO_CONCRETADA,
                       motivo_no_concretada=MotivoNoConcretada.PRECIO,
                       detalle_no_concretada="Le pareció caro el desvare nocturno.",
                       hace=4 * hora)

    def documentos(self):
        """Uno por vencer, uno vencido y los demás vigentes. Van al final: un documento vencido
        bloquea asignaciones nuevas."""
        hoy = timezone.localdate(self.ahora)
        por = self.conductores[0].usuario  # quien los registra es un usuario de la demo
        soat = TipoDocumento.objects.get(nombre="SOAT")
        tecno = TipoDocumento.objects.get(nombre="Tecnomecánica")
        licencia = TipoDocumento.objects.get(nombre="Licencia de conducción")
        carlos, diana, esteban = self.conductores
        g1, g2, g3 = self.gruas
        un_ano = timedelta(days=365)
        fechas = (
            (soat, g1, hoy + timedelta(days=max(1, soat.dias_anticipacion // 2))),  # por vencer
            (tecno, g2, hoy - timedelta(days=3)),  # vencida: Diana no recibe asignaciones nuevas
            (soat, g2, hoy + un_ano),
            (soat, g3, hoy + un_ano),
            (tecno, g1, hoy + un_ano),
            (tecno, g3, hoy + un_ano),
            (licencia, carlos, hoy + un_ano),
            (licencia, diana, hoy + un_ano),
            (licencia, esteban, hoy + un_ano),
        )
        for tipo, sujeto, vence in fechas:
            documento = registrar_documento(tipo=tipo, sujeto=sujeto, por=por, vence=vence,
                                            numero="DEMO")
            Documento.objects.filter(pk=documento.pk).update(es_demo=True)


def cargar(ahora=None) -> Resumen:
    """Carga la demo completa o nada. Lanza DemoYaCargada si ya hay, DemoEnConflicto si choca."""
    ahora = ahora or timezone.now()
    with transaction.atomic():
        if hay_demo():
            raise DemoYaCargada("Ya hay datos de demo cargados: corra demo_borrar primero.")
        cargador = _Cargador(ahora)
        _verificar_que_no_choca([f"DMO{n:03d}" for n in range(101, 200)])
        cargador.flota()
        cargador.clientes()
        cargador.servicios()
        cargador.documentos()
    # Lo mismo que hace el temporizador cada minuto y el tablero al abrirse.
    evaluar(ahora=ahora)
    return contar()


# --- Contar y borrar ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Demo:
    """Las consultas de todo lo que es de la demo, de los padres a los hijos."""

    gruas: models.QuerySet
    conductores: models.QuerySet
    usuarios: models.QuerySet
    clientes: models.QuerySet
    vehiculos: models.QuerySet
    solicitudes: models.QuerySet
    servicios: models.QuerySet
    eventos: models.QuerySet
    evidencias: models.QuerySet
    lineas: models.QuerySet
    historial: models.QuerySet
    relaciones: models.QuerySet
    documentos: models.QuerySet

    @classmethod
    def actual(cls):
        conductores = Conductor.objects.filter(es_demo=True)
        solicitudes = Solicitud.objects.filter(es_demo=True)
        servicios = Servicio.objects.filter(solicitud__in=solicitudes)
        lineas = LineaCobro.objects.filter(servicio__in=servicios)
        clientes = Cliente.objects.filter(es_demo=True)
        return cls(
            gruas=Grua.objects.filter(es_demo=True),
            conductores=conductores,
            usuarios=Usuario.objects.filter(conductor__in=conductores),
            clientes=clientes,
            vehiculos=Vehiculo.objects.filter(es_demo=True),
            solicitudes=solicitudes,
            servicios=servicios,
            eventos=EventoEstado.objects.filter(servicio__in=servicios),
            evidencias=Evidencia.objects.filter(servicio__in=servicios),
            lineas=lineas,
            historial=HistorialCobro.objects.filter(linea__in=lineas),
            relaciones=RelacionCobro.objects.filter(pagador__in=clientes),
            documentos=Documento.objects.filter(es_demo=True),
        )

    def alertas(self):
        """Las alertas que apuntan a algo de la demo (su registro es genérico: tipo + llave)."""
        condicion = Q(pk__in=[])
        for modelo, consulta in (
            (Servicio, self.servicios), (Solicitud, self.solicitudes),
            (EventoEstado, self.eventos), (Evidencia, self.evidencias),
            (LineaCobro, self.lineas), (RelacionCobro, self.relaciones),
            (Documento, self.documentos), (Conductor, self.conductores),
            (Grua, self.gruas), (Cliente, self.clientes), (Vehiculo, self.vehiculos),
        ):
            llaves = [str(pk) for pk in consulta.values_list("pk", flat=True)]
            if llaves:
                condicion |= Q(tipo_registro=ContentType.objects.get_for_model(modelo),
                               registro_id__in=llaves)
        return Alerta.objects.filter(condicion)


def contar() -> Resumen:
    demo = _Demo.actual()
    return Resumen({
        "grúas": demo.gruas.count(),
        "conductores": demo.conductores.count(),
        "clientes": demo.clientes.count(),
        "solicitudes": demo.solicitudes.count(),
        "servicios": demo.servicios.count(),
        "líneas de cobro": demo.lineas.count(),
        "documentos": demo.documentos.count(),
        "alertas abiertas": demo.alertas().filter(resuelta_en__isnull=True).count(),
    })


def _borrar_de_solo_agregar(consulta) -> None:
    """Los eventos y el historial de cobro no se borran por la vía normal (su QuerySet lo impide).
    Para la demo sí: se salta esa guarda con el borrado base de Django, solo sobre esta consulta."""
    models.QuerySet.delete(consulta)


def _describir(objetos) -> str:
    vistos = []
    for objeto in list(objetos)[:5]:
        vistos.append(f"{objeto._meta.verbose_name} «{objeto}»")
    return "; ".join(vistos)


def borrar() -> Resumen:
    """Borra toda la demo y nada más, o nada si un dato real la usa (DemoEnConflicto)."""
    antes = contar()
    archivos = []
    try:
        with transaction.atomic():
            demo = _Demo.actual()
            archivos += [e.archivo.name for e in demo.evidencias if e.archivo]
            archivos += [d.archivo.name for d in demo.documentos if d.archivo]
            demo.alertas().delete()
            NotificacionPush.objects.filter(
                Q(servicio__in=demo.servicios) | Q(dispositivo__conductor__in=demo.conductores)
            ).delete()
            TokenDispositivo.objects.filter(conductor__in=demo.conductores).delete()
            LineaEnRelacion.objects.filter(
                Q(relacion__in=demo.relaciones) | Q(linea__in=demo.lineas)
            ).delete()
            demo.relaciones.delete()
            _borrar_de_solo_agregar(demo.historial)
            demo.lineas.delete()
            demo.evidencias.delete()
            _borrar_de_solo_agregar(demo.eventos)
            demo.servicios.filter(regreso_de__isnull=False).delete()  # el regreso antes que su ida
            demo.servicios.delete()
            contactos = list(Contacto.objects.filter(
                Q(cliente__in=demo.clientes)
                | Q(pk__in=demo.solicitudes.values("contacto_origen"))
                | Q(pk__in=demo.solicitudes.values("contacto_destino"))
            ).values_list("pk", flat=True))
            demo.solicitudes.delete()
            Contacto.objects.filter(pk__in=contactos).delete()
            TelefonoCliente.objects.filter(cliente__in=demo.clientes).delete()
            Tarifa.objects.filter(cliente__in=demo.clientes).delete()
            demo.clientes.delete()
            demo.vehiculos.delete()
            demo.documentos.delete()
            AsignacionConductorGrua.objects.filter(
                Q(conductor__in=demo.conductores) | Q(grua__in=demo.gruas)
            ).delete()
            usuarios = list(demo.usuarios.values_list("pk", flat=True))
            demo.conductores.delete()
            Usuario.objects.filter(pk__in=usuarios).delete()
            demo.gruas.delete()
            # Las llaves foráneas se revisan al confirmar: si algo real apunta a la demo, falla
            # aquí y no se borra nada.
            transaction.on_commit(lambda: _borrar_archivos(archivos))
            connection.check_constraints()
    except ProtectedError as error:
        raise DemoEnConflicto(
            "No se borró nada: hay datos reales que usan datos de la demo: "
            f"{_describir(error.protected_objects)}."
        ) from error
    except IntegrityError as error:
        raise DemoEnConflicto(
            f"No se borró nada: hay datos reales que usan datos de la demo ({error})."
        ) from error
    return antes


def _borrar_archivos(nombres) -> None:
    for nombre in nombres:
        default_storage.delete(nombre)
