"""Domain services for stock adjustment (conciliacion) requests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

from django.db import transaction

from core.models import (
    Inventory,
    Location,
    Product,
    StockAdjustmentRequest,
    StockAdjustmentStatus,
    User,
)


class AdjustmentRequestError(ValueError):
    """Raised when the payload for an adjustment request is invalid."""


@dataclass(frozen=True)
class AdjustmentContext:
    product: Product
    location: Location
    system_quantity: int
    physical_quantity: int
    delta: int
    flagged: bool


def _get_tolerance() -> int:
    raw = os.getenv("ADJUSTMENT_TOLERANCE", "0")
    try:
        return max(int(raw), 0)
    except ValueError:
        return 0


def _get_product(sku: str) -> Product:
    try:
        return Product.objects.get(sku=sku)
    except Product.DoesNotExist as exc:
        raise AdjustmentRequestError(f"Producto con SKU '{sku}' no existe") from exc


def _get_location(code: str) -> Location:
    try:
        return Location.objects.get(code=code)
    except Location.DoesNotExist as exc:
        raise AdjustmentRequestError(f"Ubicacion con codigo '{code}' no existe") from exc


def _parse_quantity(value, field: str) -> int:
    try:
        qty = int(value)
    except (TypeError, ValueError) as exc:
        raise AdjustmentRequestError(f"{field} debe ser un numero entero") from exc
    if qty < 0:
        raise AdjustmentRequestError(f"{field} debe ser mayor o igual a 0")
    return qty


def _build_context(payload: Dict[str, object]) -> AdjustmentContext:
    sku = str(payload.get("sku", "")).strip()
    location_code = str(payload.get("location_code", "")).strip()
    if not sku:
        raise AdjustmentRequestError("Debe enviar el SKU del producto")
    if not location_code:
        raise AdjustmentRequestError("Debe enviar el codigo de ubicacion")

    product = _get_product(sku)
    location = _get_location(location_code)

    physical_qty = _parse_quantity(payload.get("physical_quantity"), "physical_quantity")
    system_record = (
        Inventory.objects.filter(product=product, location=location).values("quantity").first()
    )
    system_qty = int(system_record["quantity"]) if system_record else 0
    delta = physical_qty - system_qty

    if delta == 0:
        raise AdjustmentRequestError("La diferencia es cero; no se requiere ajuste")

    tolerance = _get_tolerance()
    flagged = abs(delta) > tolerance if tolerance else False

    return AdjustmentContext(
        product=product,
        location=location,
        system_quantity=system_qty,
        physical_quantity=physical_qty,
        delta=delta,
        flagged=flagged,
    )


@transaction.atomic
def create_adjustment_request(
    payload: Dict[str, object],
    created_by: Optional[User] = None,
) -> StockAdjustmentRequest:
    """
    Registers a new stock adjustment request. Calculates delta automatically and
    marks the request as flagged if it exceeds the tolerance configured via env.
    """
    reason = str(payload.get("reason", "")).strip()
    if not reason:
        raise AdjustmentRequestError("Debe proporcionar un motivo (reason)")

    context = _build_context(payload)
    attachment_url = str(payload.get("attachment_url") or "").strip()

    request = StockAdjustmentRequest.objects.create(
        product=context.product,
        location=context.location,
        system_quantity=context.system_quantity,
        physical_quantity=context.physical_quantity,
        delta=context.delta,
        reason=reason,
        attachment_url=attachment_url,
        status=StockAdjustmentStatus.PENDING,
        flagged=context.flagged,
        created_by=created_by,
    )
    return request


def list_adjustment_requests(filters: Optional[Dict[str, str]] = None):
    """
    Returns a queryset filtered according to status, product sku, location code.
    """
    qs = StockAdjustmentRequest.objects.select_related("product", "location", "created_by")
    if not filters:
        return qs

    status = (filters.get("status") or "").strip().lower()
    if status:
        qs = qs.filter(status=status)

    sku = (filters.get("product") or "").strip()
    if sku:
        qs = qs.filter(product__sku__iexact=sku)

    location_code = (filters.get("location") or "").strip()
    if location_code:
        qs = qs.filter(location__code__iexact=location_code)

    flagged = filters.get("flagged")
    if flagged in {"true", "false"}:
        qs = qs.filter(flagged=(flagged == "true"))

    return qs


def get_adjustment_request(pk: int) -> StockAdjustmentRequest:
    return (
        StockAdjustmentRequest.objects.select_related("product", "location", "created_by")
        .get(pk=pk)
    )


__all__ = [
    "AdjustmentRequestError",
    "create_adjustment_request",
    "list_adjustment_requests",
    "get_adjustment_request",
    "StockAdjustmentStatus",
]
