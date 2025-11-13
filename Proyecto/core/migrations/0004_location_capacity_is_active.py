from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_internaltransfer"),
    ]

    operations = [
        migrations.AddField(
            model_name="location",
            name="capacity",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="location",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
