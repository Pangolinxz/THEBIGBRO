from django.contrib import admin
from .models import (
    Rol,
    User,
    Product,
    Location,
    Inventory,
    InventoryTransaction,
    Order,
    OrderItem,
    StockAlert,
    StockAdjustmentRequest,
    InventoryAudit,
)

admin.site.register(Rol)
admin.site.register(User)
admin.site.register(Product)
admin.site.register(Location)
admin.site.register(Inventory)
admin.site.register(InventoryTransaction)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(StockAlert)
admin.site.register(StockAdjustmentRequest)
admin.site.register(InventoryAudit)
