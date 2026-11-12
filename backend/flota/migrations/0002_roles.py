"""Roles de Arribo como grupos de Django. Los permisos de cada rol los asignan las tareas que los usan."""
from django.db import migrations

ROLES = ["administrador", "logistica", "facturacion", "conductor"]


def crear_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for nombre in ROLES:
        Group.objects.get_or_create(name=nombre)


def quitar_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):

    dependencies = (
        ("auth", "0012_alter_user_first_name_max_length"),
        ("flota", "0001_inicial"),
    )

    operations = (
        migrations.RunPython(crear_roles, quitar_roles),
    )
