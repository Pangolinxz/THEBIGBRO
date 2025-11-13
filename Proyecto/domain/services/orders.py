"""Services for order dispatching (RF08)."""

from __future__ import annotations

from typing import Dict, Optional

from django.db import transaction
from django.utils import timezone

from core.models import (
    Inventory,
    InventoryAudit,
    InventoryTransaction,
    Order,
    OrderItem,
    OrderStatus,
    Product,
    Location,
    User,
    DeliveryAlert,
)


class OrderDispatchError(ValueError):
    """Raised when an order cannot be dispatched/reserved/closed."""


def list_orders(filters: Optional[Dict[str, str]] = None):
    qs = (
        Order.objects.select_related("seller_id", "delivery_alert")
        .prefetch_related("orderitem_set__product", "orderitem_set__location")
    )
    if not filters:
        return qs
    status = (filters.get("status") or "").strip().lower()
    if status:
        qs = qs.filter(status=status)
    order_id = filters.get("order_id")
    if order_id:
        qs = qs.filter(pk=order_id)
    return qs


@transaction.atomic
def reserve_order(order_id: int, operator: Optional[User]) -> Order:
    order = (
        Order.objects.select_for_update()
        .prefetch_related("orderitem_set__product", "orderitem_set__location")
        .get(pk=order_id)
    )
    if order.status not in {OrderStatus.CREATED, OrderStatus.RESERVED}:
        raise OrderDispatchError("El pedido no puede reservarse en su estado actual.")

    items = list(order.orderitem_set.all())
    if not items:
        raise OrderDispatchError("El pedido no tiene ítems para reservar.")

    for item in items:
        if not item.location:
            raise OrderDispatchError(
                f"El ítem {item.product.sku} no tiene ubicación asignada."
            )
        inventory = (
            Inventory.objects.select_for_update()
            .filter(product=item.product, location=item.location)
            .first()
        )
        if inventory is None or inventory.quantity < item.quantity:
            raise OrderDispatchError(
                f"Inventario insuficiente para reservar {item.product.sku} en {item.location.code}."
            )

    order.orderitem_set.update(reserved=True)
    order.status = OrderStatus.RESERVED
    order.save(update_fields=["status"])
    return order


@transaction.atomic
def dispatch_order(
    order_id: int,
    operator: Optional[User],
) -> Order:
    order = (
        Order.objects.select_for_update()
        .select_related("delivery_alert")
        .prefetch_related("orderitem_set__product", "orderitem_set__location")
        .get(pk=order_id)
    )
    if order.status != OrderStatus.RESERVED:
        raise OrderDispatchError("El pedido no está en estado RESERVADO.")

    items = list(order.orderitem_set.all())
    if not items:
        raise OrderDispatchError("El pedido no tiene ítems asociados.")

    now = timezone.now()
    for item in items:
        if not item.location:
            raise OrderDispatchError(
                f"El ítem {item.product.sku} no tiene ubicación asignada."
            )

        inventory = (
            Inventory.objects.select_for_update()
            .filter(product=item.product, location=item.location)
            .first()
        )
        if inventory is None or inventory.quantity < item.quantity:
            raise OrderDispatchError(
                f"Inventario insuficiente para {item.product.sku} en {item.location.code}."
            )

        previous_stock = inventory.quantity
        inventory.quantity = previous_stock - item.quantity
        inventory.updated_at = now
        inventory.save(update_fields=["quantity", "updated_at"])

        InventoryTransaction.objects.create(
            product=item.product,
            location=item.location,
            user=operator,
            type="order-dispatch",
            quantity=item.quantity,
            created_at=now,
        )

        InventoryAudit.objects.create(
            product=item.product,
            location=item.location,
            user=operator,
            movement_type=InventoryAudit.MOVEMENT_EGRESS,
            quantity=item.quantity,
            previous_stock=previous_stock,
            new_stock=inventory.quantity,
            observations=f"Despacho de pedido #{order.id}",
        )

        item.reserved = False
        item.save(update_fields=["reserved"])

    order.departure_time = now
    order.actual_arrival_time = None
    order.status = OrderStatus.DISPATCHED
    order.save(update_fields=["status", "departure_time", "actual_arrival_time"])

    alert = getattr(order, "delivery_alert", None)
    if order.estimated_arrival_time:
        local_eta = timezone.localtime(order.estimated_arrival_time)
        message = (
            f"Pedido #{order.id} en ruta. ETA {local_eta.strftime('%Y-%m-%d %H:%M')}"
        )
        if alert:
            alert.due_time = order.estimated_arrival_time
            alert.message = message
            alert.resolved = False
            alert.save(update_fields=["due_time", "message", "resolved"])
        else:
            DeliveryAlert.objects.create(
                order=order,
                due_time=order.estimated_arrival_time,
                message=message,
            )
    elif alert and not alert.resolved:
        alert.resolved = True
        alert.save(update_fields=["resolved"])

    return order


@transaction.atomic
def close_order(order_id: int, operator: Optional[User]) -> Order:
    order = (
        Order.objects.select_for_update()
        .select_related("delivery_alert")
        .get(pk=order_id)
    )
    if order.status != OrderStatus.DISPATCHED:
        raise OrderDispatchError("Solo puedes cerrar pedidos en estado DESPACHADO.")

    now = timezone.now()
    order.status = OrderStatus.CLOSED
    order.actual_arrival_time = now
    order.save(update_fields=["status", "actual_arrival_time"])

    alert = getattr(order, "delivery_alert", None)
    if alert and not alert.resolved:
        alert.resolved = True
        alert.save(update_fields=["resolved"])

    return order


__all__ = [
    "OrderDispatchError",
    "dispatch_order",
    "reserve_order",
    "close_order",
    "list_orders",
]
