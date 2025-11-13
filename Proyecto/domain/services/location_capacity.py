"""Helpers to evaluate capacity/ocupation per location."""

from __future__ import annotations

from typing import Optional

from django.db.models import Sum

from core.models import Inventory, Location


def location_total_stock(
    location: Location,
    exclude_inventory_id: Optional[int] = None,
) -> int:
    """
    Returns the total quantity stored in the given location, optionally
    excluding a specific Inventory row (useful when projecting updates).
    Locks rows with SELECT ... FOR UPDATE so callers in transactions get
    a consistent snapshot.
    """
    qs = Inventory.objects.select_for_update().filter(location=location)
    if exclude_inventory_id:
        qs = qs.exclude(pk=exclude_inventory_id)
    total = qs.aggregate(total=Sum("quantity")).get("total") or 0
    return int(total)


__all__ = ["location_total_stock"]
