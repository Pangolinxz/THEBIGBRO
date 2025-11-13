"""Helpers to compute dashboard KPIs (RF07/RF19/RF20)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from django.db.models import Sum, F, Count, Q
from django.db.models.functions import Coalesce
from django.db.models.functions import TruncDate
from django.utils import timezone

from core.models import (
    Inventory,
    InventoryTransaction,
    Order,
    OrderItem,
    Product,
    StockAlert,
)


def _parse_date(value: Optional[date], default: date) -> date:
    return value or default


def get_dashboard_metrics(filters: Optional[Dict[str, object]] = None) -> Dict[str, List]:
    filters = filters or {}
    product = filters.get("product")
    location = filters.get("location")
    now = timezone.now()
    default_end = now.date()
    default_start = default_end - timedelta(days=30)
    date_from = _parse_date(filters.get("date_from"), default_start)
    date_to = _parse_date(filters.get("date_to"), default_end)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    transactions = InventoryTransaction.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    if product:
        transactions = transactions.filter(product=product)
    if location:
        transactions = transactions.filter(location=location)

    inventory_qs = Inventory.objects.all()
    if product:
        inventory_qs = inventory_qs.filter(product=product)
    if location:
        inventory_qs = inventory_qs.filter(location=location)

    daily_movements = (
        transactions.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Sum("quantity"))
        .order_by("day")
    )

    inventory_by_product = (
        inventory_qs.values("product__sku", "product__name")
        .annotate(total=Sum("quantity"))
        .order_by("-total")[:5]
    )

    total_inventory_qty = (
        inventory_qs.aggregate(total=Sum("quantity")).get("total") or 0
    )
    total_products = (
        1 if product else Product.objects.count()
    )

    ingress_today = (
        transactions.filter(
            created_at__date=date_to,
            type__icontains="ingres",
        ).aggregate(total=Sum("quantity")).get("total")
        or 0
    )
    egress_today = (
        transactions.filter(
            created_at__date=date_to,
            type__icontains="egres",
        ).aggregate(total=Sum("quantity")).get("total")
        or 0
    )

    auto_alert_qs = Inventory.objects.annotate(
        target_reorder=Coalesce("custom_reorder_point", "product__reorder_point")
    ).filter(quantity__lt=F("target_reorder"))
    if product:
        auto_alert_qs = auto_alert_qs.filter(product=product)
    if location:
        auto_alert_qs = auto_alert_qs.filter(location=location)
    auto_alert_count = auto_alert_qs.count()
    manual_alert_count = StockAlert.objects.count()

    total_egress = (
        transactions.filter(type__icontains="egres")
        .aggregate(total=Sum("quantity"))
        .get("total")
        or 0
    )
    days_range = max((date_to - date_from).days + 1, 1)
    avg_daily_egress = total_egress / days_range if days_range else 0
    inventory_turnover = (
        round(total_egress / total_inventory_qty, 2)
        if total_inventory_qty and total_egress
        else None
    )
    days_of_inventory = (
        round(total_inventory_qty / avg_daily_egress, 1)
        if avg_daily_egress
        else None
    )

    order_items = OrderItem.objects.all()
    if product:
        order_items = order_items.filter(product=product)
    fulfilled_qty = (
        order_items.filter(reserved=True).aggregate(total=Sum("quantity")).get("total")
        or 0
    )
    total_items = order_items.aggregate(total=Sum("quantity")).get("total") or 0
    fill_rate = round((fulfilled_qty / total_items) * 100, 1) if total_items else None

    orders = Order.objects.all()
    if product:
        orders = orders.filter(orderitem__product=product).distinct()
    orders_by_status = list(
        orders.values("status").annotate(total=Count("id")).order_by("status")
    )

    inventory_by_location = (
        inventory_qs.values("location__code", "location__description")
        .annotate(total=Sum("quantity"))
        .order_by("location__code")
    )

    movements_by_location = (
        transactions.values("location__code")
        .annotate(
            total_movements=Count("id"),
            ingress_qty=Sum(
                "quantity", filter=Q(type__icontains="ingres")
            ),
            egress_qty=Sum(
                "quantity", filter=Q(type__icontains="egres")
            ),
        )
        .order_by("location__code")
    )

    return {
        "daily_movements": list(daily_movements),
        "top_products_out": list(inventory_by_product),
        "inventory_by_location": list(inventory_by_location),
        "movements_by_location": list(movements_by_location),
        "total_products": total_products,
        "ingress_today": ingress_today,
        "egress_today": egress_today,
        "auto_alert_count": auto_alert_count,
        "manual_alert_count": manual_alert_count,
        "inventory_turnover": inventory_turnover,
        "fill_rate": fill_rate,
        "days_of_inventory": days_of_inventory,
        "orders_by_status": orders_by_status,
        "total_inventory_quantity": total_inventory_qty,
        "date_from": date_from,
        "date_to": date_to,
    }


__all__ = ["get_dashboard_metrics"]
