from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_order_customer_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="contact_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="order",
            name="contact_phone",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("cash", "Efectivo"),
                    ("card", "Tarjeta"),
                    ("transfer", "Transferencia"),
                    ("other", "Otro"),
                ],
                default="cash",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="departure_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="estimated_arrival_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="actual_arrival_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="DeliveryAlert",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("due_time", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("resolved", models.BooleanField(default=False)),
                ("message", models.TextField(blank=True)),
                (
                    "order",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="delivery_alert",
                        to="core.order",
                    ),
                ),
            ],
            options={"db_table": "delivery_alert"},
        ),
    ]
