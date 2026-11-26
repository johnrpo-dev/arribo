from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = (
        ('solicitudes', '0008_numero_de_bodega'),
    )

    operations = (
        migrations.AddField(
            model_name='eventoestado',
            name='inicio_excedido',
            field=models.BooleanField(default=False, help_text='En camino aplicado aunque el conductor ya tenía tantos servicios iniciados sin finalizar como puestos tiene la grúa (celular desactualizado).', verbose_name='inicio excedido'),
        ),
    )
