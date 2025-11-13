from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_order_status_orderitem_location"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="customer_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="order",
            name="customer_address",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="order",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
