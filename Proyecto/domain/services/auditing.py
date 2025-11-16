"""Services to fetch audit (inventory transaction) logs with filters."""

from __future__ import annotations

from typing import Dict, Optional
from django.utils.dateparse import parse_datetime, parse_date

from core.models import InventoryTransaction


def _parse_date_range(filters: Dict[str, str]) -> Dict[str, str]:
    range_filters: Dict[str, str] = {}
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")

    if date_from:
        dt_from = parse_datetime(date_from) or parse_date(date_from)
        if dt_from:
            range_filters["created_at__gte"] = dt_from
    if date_to:
        dt_to = parse_datetime(date_to) or parse_date(date_to)
        if dt_to:
            range_filters["created_at__lte"] = dt_to
    return range_filters


def get_audit_logs(filters: Optional[Dict[str, str]] = None):
    qs = InventoryTransaction.objects.select_related("product", "location", "user")
    if not filters:
        return qs.order_by("-created_at")

    filters = filters or {}
    range_filters = _parse_date_range(filters)
    if range_filters:
        qs = qs.filter(**range_filters)

    user_id = filters.get("user_id")
    if user_id:
        qs = qs.filter(user_id=user_id)

    product_id = filters.get("product_id")
    if product_id:
        qs = qs.filter(product_id=product_id)

    product_sku = (filters.get("product_sku") or filters.get("sku") or "").strip()
    if product_sku:
        qs = qs.filter(product__sku__iexact=product_sku)

    location_id = filters.get("location_id")
    if location_id:
        qs = qs.filter(location_id=location_id)

    action = filters.get("action")
    if action:
        qs = qs.filter(type__iexact=action)

    ordering = filters.get("ordering", "-created_at")
    if ordering not in {"-created_at", "created_at", "user", "-user"}:
        ordering = "-created_at"
    if ordering in {"user", "-user"}:
        user_order = "user__username"
        if ordering.startswith("-"):
            user_order = f"-{user_order}"
        qs = qs.order_by(user_order, "-created_at")
    else:
        qs = qs.order_by(ordering)
    return qs
