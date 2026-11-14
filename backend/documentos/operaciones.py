"""Registrar documentos. Un documento no se edita ni se borra: el nuevo reemplaza al anterior del
mismo tipo para esa grúa o conductor, y el anterior queda en el historial."""
from datetime import date

from django.db import transaction

from flota.models import Conductor, Grua

from .models import AplicaA, Documento, TipoDocumento


class DocumentoInvalido(Exception):
    """El documento no se puede registrar así (el mensaje dice por qué, en español)."""


def registrar_documento(
    *,
    tipo: TipoDocumento,
    sujeto: Grua | Conductor,
    por,
    vence: date | None = None,
    aplica_desde: date | None = None,
    numero: str = "",
    archivo=None,
    tipo_archivo: str = "",
) -> Documento:
    """Guarda un documento nuevo, que pasa a ser el vigente de su tipo para `sujeto`.

    `archivo` es un archivo subido de Django ya validado (tipo y tamaño) que está en disco;
    `tipo_archivo` es el que se reconoció por su contenido. La base repite las reglas de coherencia.
    """
    if not tipo.activo:
        raise DocumentoInvalido(f"El tipo {tipo} está inactivo: no se registran documentos de él.")
    es_grua = isinstance(sujeto, Grua)
    if (tipo.aplica_a == AplicaA.GRUA) != es_grua:
        lado = "una grúa" if tipo.aplica_a == AplicaA.GRUA else "un conductor"
        raise DocumentoInvalido(f"El tipo {tipo} es de {lado}.")
    if (vence is None) == (aplica_desde is None):
        raise DocumentoInvalido(
            "Escriba la fecha de vencimiento o, si aún no aplica, la fecha desde la que aplica."
        )
    if bool(archivo) != bool(tipo_archivo):
        raise DocumentoInvalido("El archivo adjunto necesita su tipo reconocido.")
    documento = Documento(
        tipo=tipo,
        aplica_a=tipo.aplica_a,
        grua=sujeto if es_grua else None,
        conductor=None if es_grua else sujeto,
        numero=numero.strip(),
        vence=vence,
        aplica_desde=aplica_desde,
        tipo_archivo=tipo_archivo if archivo else "",
        registrado_por=por,
    )
    if archivo:
        documento.archivo = archivo
    try:
        with transaction.atomic():
            documento.save()
    except Exception:
        # El archivo ya se movió a MEDIA_ROOT antes del INSERT: si la fila no quedó, sobra.
        if documento.archivo.name:
            documento.archivo.storage.delete(documento.archivo.name)
        raise
    return documento


def historial(tipo: TipoDocumento, sujeto: Grua | Conductor):
    """Todos los documentos de ese tipo para ese sujeto, el vigente primero."""
    filtro = {"grua": sujeto} if isinstance(sujeto, Grua) else {"conductor": sujeto}
    return (
        Documento.objects.filter(tipo=tipo, **filtro)
        .select_related("registrado_por")
        .order_by("-registrado_en", "-pk")
    )
