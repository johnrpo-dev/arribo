"""Pantallas de documentos de la sección Flota y personal (solo administrador: lo aplica
`documentos/urls.py` con `requiere_rol`). La lista con el resumen está en `flota/views.py`; aquí,
el estado e historial de un tipo para una grúa o un conductor, los archivos y los tipos."""
from django.contrib import messages
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render

from flota.models import Conductor, Grua

from . import consultas
from .archivos import con_archivo_a_disco
from .formularios import FormularioDocumento, FormularioTipo
from .models import AplicaA, Documento, TipoArchivo, TipoDocumento
from .operaciones import DocumentoInvalido, historial, registrar_documento

TIPO_DE_CONTENIDO = {
    TipoArchivo.JPEG: "image/jpeg",
    TipoArchivo.PNG: "image/png",
    TipoArchivo.PDF: "application/pdf",
}


@con_archivo_a_disco
def documento_de_grua(request, pk, tipo_pk):
    return _documento(request, get_object_or_404(Grua, pk=pk), tipo_pk, AplicaA.GRUA)


@con_archivo_a_disco
def documento_de_conductor(request, pk, tipo_pk):
    return _documento(request, get_object_or_404(Conductor, pk=pk), tipo_pk, AplicaA.CONDUCTOR)


def _documento(request, sujeto, tipo_pk, aplica_a):
    """Estado e historial de un tipo de documento de una grúa o un conductor; registrar uno nuevo."""
    tipo = get_object_or_404(TipoDocumento, pk=tipo_pk, aplica_a=aplica_a)
    formulario = None
    if tipo.activo:
        formulario = FormularioDocumento(
            request.POST or None,
            request.FILES or None,
            archivo_excedido=request.method == "POST" and request.archivo_excedido(),
        )
        if request.method == "POST" and formulario.is_valid():
            datos = formulario.cleaned_data
            try:
                registrar_documento(
                    tipo=tipo,
                    sujeto=sujeto,
                    por=request.user,
                    vence=datos["vence"],
                    aplica_desde=datos["aplica_desde"],
                    numero=datos["numero"],
                    archivo=datos["archivo"],
                    tipo_archivo=formulario.tipo_archivo,
                )
            except DocumentoInvalido as error:
                formulario.add_error(None, str(error))
            else:
                messages.success(request, f"{tipo} registrado. Reemplaza al anterior.")
                return redirect(request.path)
    elif request.method == "POST":
        messages.error(request, f"El tipo {tipo} está inactivo: no se registran documentos de él.")
    return render(
        request,
        "documentos/documento.html",
        {
            "tipo": tipo,
            "sujeto": sujeto,
            "es_grua": aplica_a == AplicaA.GRUA,
            "estado": consultas.estado_de_tipo(sujeto, tipo),
            "historial": historial(tipo, sujeto),
            "formulario": formulario,
        },
    )


def archivo(request, pk):
    """El archivo de un documento, para verlo en el navegador. No hay URL pública de MEDIA."""
    documento = get_object_or_404(Documento, pk=pk)
    if not documento.archivo:
        raise Http404("El documento no tiene archivo.")
    try:
        abierto = documento.archivo.open("rb")
    except FileNotFoundError as error:
        raise Http404("El archivo no está en el servidor.") from error
    return FileResponse(abierto, content_type=TIPO_DE_CONTENIDO[documento.tipo_archivo])


def tipos(request):
    """Lista de tipos de documento y formulario para crear uno."""
    formulario = FormularioTipo(request.POST or None)
    if request.method == "POST" and formulario.is_valid():
        tipo = formulario.save()
        messages.success(request, f"Tipo {tipo} creado.")
        return redirect("tipos_documento")
    return render(
        request,
        "documentos/tipos.html",
        {"tipos": TipoDocumento.objects.order_by("-activo", "aplica_a", "nombre"),
         "formulario": formulario},
    )


def editar_tipo(request, pk):
    """Editar o desactivar un tipo. No se borra: un tipo inactivo no se exige ni bloquea."""
    tipo = get_object_or_404(TipoDocumento, pk=pk)
    formulario = FormularioTipo(request.POST or None, instance=tipo)
    if request.method == "POST" and formulario.is_valid():
        formulario.save()
        messages.success(request, f"Tipo {formulario.instance} guardado.")
        return redirect("tipos_documento")
    return render(request, "documentos/tipo.html", {"tipo": tipo, "formulario": formulario})
