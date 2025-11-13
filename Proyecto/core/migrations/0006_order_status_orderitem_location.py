from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_inventory_custom_reorder_point_internaltransfer_destination_reorder"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("created", "Creado"),
                    ("reserved", "Reservado"),
                    ("dispatched", "Despachado"),
                    ("closed", "Cerrado"),
                ],
                default="created",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="location",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=models.PROTECT, to="core.location"
            ),
        ),
    ]
