from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='category',
            field=models.CharField(
                choices=[
                    ('standard', 'Producto estandar'),
                    ('perishable', 'Perecedero'),
                    ('fragile', 'Fragil'),
                    ('bulk', 'Voluminoso'),
                    ('hazardous', 'Peligroso'),
                ],
                default='standard',
                max_length=32,
            ),
        ),
    ]
