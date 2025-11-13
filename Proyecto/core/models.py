from django.db import models
from django.contrib.auth.models import AbstractUser

class ProductCategory(models.TextChoices):
    STANDARD = "standard", "Producto estandar"
    PERISHABLE = "perishable", "Perecedero"
    FRAGILE = "fragile", "Fragil"
    BULK = "bulk", "Voluminoso"
    HAZARDOUS = "hazardous", "Peligroso"


class StockAdjustmentStatus(models.TextChoices):
    PENDING = "pending", "Pendiente"
    APPROVED = "approved", "Aprobado"
    REJECTED = "rejected", "Rechazado"

class TransferStatus(models.TextChoices):
    PENDING = "pending", "Pendiente"
    APPROVED = "approved", "Aprobada"
    REJECTED = "rejected", "Rechazada"

class OrderStatus(models.TextChoices):
    CREATED = "created", "Creado"
    RESERVED = "reserved", "Reservado"
    DISPATCHED = "dispatched", "Despachado"
    CLOSED = "closed", "Cerrado"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Efectivo"
    CARD = "card", "Tarjeta"
    TRANSFER = "transfer", "Transferencia"
    OTHER = "other", "Otro"

class Rol(models.Model):
    name = models.CharField(max_length=255, unique=True)
    class Meta:
        db_table = 'rol'
    def __str__(self):
        return self.name

class User(AbstractUser):
    username = models.CharField(max_length=255, unique=True)
    full_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.CharField(max_length=255, unique=True)
    role = models.ForeignKey(Rol, null=True, blank=True, on_delete=models.SET_NULL)
    password = models.CharField(max_length=128, blank=True) 
    class Meta:
        db_table = 'user'
    def __str__(self):
        return self.username

class Product(models.Model):
    sku = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    reorder_point = models.IntegerField(default=0)
    category = models.CharField(
        max_length=32,
        choices=ProductCategory.choices,
        default=ProductCategory.STANDARD,
    )
    class Meta:
        db_table = 'product'
    def __str__(self):
        return f"{self.sku} - {self.name} ({self.get_category_display()})"

class Location(models.Model):
    code = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    capacity = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    class Meta:
        db_table = 'location'
    def __str__(self):
        return self.code

class Inventory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    updated_at = models.DateTimeField()
    custom_reorder_point = models.IntegerField(null=True, blank=True)
    class Meta:
        db_table = 'inventory'
        constraints = [models.UniqueConstraint(fields=['product', 'location'], name='inventory_index_0')]
    def __str__(self):
        return f"{self.product} @ {self.location} = {self.quantity}"

    @property
    def effective_reorder_point(self) -> int:
        if self.custom_reorder_point is not None:
            return self.custom_reorder_point
        return self.product.reorder_point

class InventoryTransaction(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    type = models.CharField(max_length=255)
    quantity = models.IntegerField()
    created_at = models.DateTimeField()
    class Meta:
        db_table = 'inventory_transaction'

class Order(models.Model):
    seller_id = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(
        max_length=32,
        choices=OrderStatus.choices,
        default=OrderStatus.CREATED,
    )
    customer_name = models.CharField(max_length=255, blank=True)
    customer_address = models.TextField(blank=True)
    contact_name = models.CharField(max_length=255, blank=True)
    contact_phone = models.CharField(max_length=64, blank=True)
    payment_method = models.CharField(
        max_length=32,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    departure_time = models.DateTimeField(null=True, blank=True)
    estimated_arrival_time = models.DateTimeField(null=True, blank=True)
    actual_arrival_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        db_table = 'order'

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    reserved = models.BooleanField(default=False)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, null=True, blank=True)
    class Meta:
        db_table = 'order_item'


class DeliveryAlert(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="delivery_alert")
    due_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)
    message = models.TextField(blank=True)

    class Meta:
        db_table = "delivery_alert"

class StockAlert(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    triggered_at = models.DateTimeField()
    message = models.TextField(blank=True)
    class Meta:
        db_table = 'stock_alert'


class StockAdjustmentRequest(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    system_quantity = models.IntegerField()
    physical_quantity = models.IntegerField()
    delta = models.IntegerField()
    reason = models.TextField()
    attachment_url = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=StockAdjustmentStatus.choices,
        default=StockAdjustmentStatus.PENDING,
    )
    flagged = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_adjustments',
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    resolution_comment = models.TextField(blank=True)

    class Meta:
        db_table = 'stock_adjustment_request'
        ordering = ["-created_at"]

    def __str__(self):
        return f"Adjustment {self.id} - {self.product.sku} ({self.status})"


class InventoryAudit(models.Model):
    MOVEMENT_INGRESS = "ingreso"
    MOVEMENT_EGRESS = "egreso"

    MOVEMENT_CHOICES = (
        (MOVEMENT_INGRESS, "Ingreso"),
        (MOVEMENT_EGRESS, "Egreso"),
    )

    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_CHOICES)
    quantity = models.PositiveIntegerField()
    previous_stock = models.IntegerField()
    new_stock = models.IntegerField()
    observations = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inventory_audit'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.movement_type} {self.quantity} {self.product.sku} @ {self.location.code}"


class InternalTransfer(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    origin_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="origin_transfers",
    )
    destination_location = models.ForeignKey(
        Location,
        on_delete=models.PROTECT,
        related_name="destination_transfers",
    )
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=32,
        choices=TransferStatus.choices,
        default=TransferStatus.PENDING,
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_transfers",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_transfers",
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    resolution_comment = models.TextField(blank=True)
    destination_reorder_point = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "internal_transfer"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Transfer {self.id} - {self.product.sku} ({self.status})"
