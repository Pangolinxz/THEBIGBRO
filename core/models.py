from django.db import models

class Rol(models.Model):
    name = models.CharField(max_length=255, unique=True)
    class Meta:
        db_table = 'rol'
    def __str__(self):
        return self.name

class User(models.Model):
    username = models.CharField(max_length=255, unique=True)
    full_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.CharField(max_length=255, unique=True)
    role = models.ForeignKey(Rol, null=True, blank=True, on_delete=models.SET_NULL)
    class Meta:
        db_table = 'user'
    def __str__(self):
        return self.username

class Product(models.Model):
    sku = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    reorder_point = models.IntegerField(default=0)
    class Meta:
        db_table = 'product'
    def __str__(self):
        return f"{self.sku} - {self.name}"

class Location(models.Model):
    code = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    class Meta:
        db_table = 'location'
    def __str__(self):
        return self.code

class Inventory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    updated_at = models.DateTimeField()
    class Meta:
        db_table = 'inventory'
        constraints = [models.UniqueConstraint(fields=['product', 'location'], name='inventory_index_0')]
    def __str__(self):
        return f"{self.product} @ {self.location} = {self.quantity}"

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
    seller = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=255)
    created_at = models.DateTimeField()
    class Meta:
        db_table = 'order'

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    reserved = models.BooleanField(default=False)
    class Meta:
        db_table = 'order_item'

class StockAlert(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    triggered_at = models.DateTimeField()
    message = models.TextField(blank=True)
    class Meta:
        db_table = 'stock_alert'
