"""Tipos de documento iniciales (docs/arquitectura.md): SOAT y tecnomecánica de la grúa, licencia de
conducción del conductor, con aviso desde 30 días antes. Son el valor por defecto: la lista se edita
en el panel. Si ya existe un tipo con el mismo nombre, no se toca."""
from django.db import migrations

TIPOS_INICIALES = (
    ("SOAT", "grua"),
    ("Tecnomecánica", "grua"),
    ("Licencia de conducción", "conductor"),
)


def sembrar(apps, schema_editor):
    TipoDocumento = apps.get_model("documentos", "TipoDocumento")
    for nombre, aplica_a in TIPOS_INICIALES:
        if not TipoDocumento.objects.filter(nombre__iexact=nombre).exists():
            TipoDocumento.objects.create(nombre=nombre, aplica_a=aplica_a, dias_anticipacion=30)


class Migration(migrations.Migration):

    dependencies = (("documentos", "0001_inicial"),)

    # Al revertir no se borra nada: los tipos pueden tener documentos.
    operations = (migrations.RunPython(sembrar, migrations.RunPython.noop),)
