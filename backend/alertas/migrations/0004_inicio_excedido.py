from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = (
        ('alertas', '0003_alertas_por_umbral'),
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    )

    operations = (
        migrations.RemoveConstraint(
            model_name='alerta',
            name='alerta_tipo_valido',
        ),
        migrations.AlterField(
            model_name='alerta',
            name='tipo',
            field=models.CharField(choices=[('conflicto_sincronizacion', 'Conflicto de sincronización'), ('capacidad_excedida', 'Capacidad de la grúa excedida'), ('inicio_excedido', 'Servicio iniciado sin finalizar el anterior'), ('evento_rechazado', 'Evento de la app que no se pudo guardar'), ('identificacion_por_revisar', 'Placa o VIN digitado por revisar'), ('sin_asignar', 'Servicio sin asignar'), ('recogido_sin_entregado', 'Recogido sin Entregado'), ('documento_por_vencer', 'Documento por vencer o vencido')], max_length=40, verbose_name='tipo'),
        ),
        migrations.AddConstraint(
            model_name='alerta',
            constraint=models.CheckConstraint(condition=models.Q(('tipo__in', ['conflicto_sincronizacion', 'capacidad_excedida', 'inicio_excedido', 'evento_rechazado', 'identificacion_por_revisar', 'sin_asignar', 'recogido_sin_entregado', 'documento_por_vencer'])), name='alerta_tipo_valido', violation_error_message='Tipo de alerta desconocido.'),
        ),
    )
