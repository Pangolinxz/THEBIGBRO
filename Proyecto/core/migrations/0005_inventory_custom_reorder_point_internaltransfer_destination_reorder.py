from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0004_location_capacity_is_active"),
    ]

    operations = [
        migrations.AddField(
            model_name="inventory",
            name="custom_reorder_point",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="internaltransfer",
            name="destination_reorder_point",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]
