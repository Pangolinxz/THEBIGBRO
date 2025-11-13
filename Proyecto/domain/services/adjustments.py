"""Domain services for stock adjustment (conciliacion) requests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional

from django.db import transaction
from django.utils import timezone

from core.models import (
    Inventory,
    InventoryAudit,
    InventoryTransaction,
    Location,
    Product,
    StockAdjustmentRequest,
    StockAdjustmentStatus,
    User,
)
from domain.services.location_capacity import location_total_stock


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


def get_adjustment_tolerance() -> int:
    """Expose current tolerance so UI layers can communicate the rule."""
    return _get_tolerance()


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
    qs = StockAdjustmentRequest.objects.select_related(
        "product",
        "location",
        "created_by",
        "processed_by",
    )
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
        StockAdjustmentRequest.objects.select_related(
            "product",
            "location",
            "created_by",
            "processed_by",
        ).get(pk=pk)
    )


def _validate_pending(adjustment: StockAdjustmentRequest) -> None:
    if adjustment.status != StockAdjustmentStatus.PENDING:
        raise AdjustmentRequestError("El ajuste ya fue procesado.")


def _movement_type_from_delta(delta: int) -> str:
    if delta >= 0:
        return InventoryAudit.MOVEMENT_INGRESS
    return InventoryAudit.MOVEMENT_EGRESS


@transaction.atomic
def approve_adjustment(
    adjustment_id: int,
    supervisor_user: Optional[User],
    comment: str = "",
) -> StockAdjustmentRequest:
    adjustment = StockAdjustmentRequest.objects.select_for_update().select_related(
        "product", "location"
    ).get(pk=adjustment_id)
    _validate_pending(adjustment)

    now = timezone.now()
    inventory, _ = Inventory.objects.select_for_update().get_or_create(
        product=adjustment.product,
        location=adjustment.location,
        defaults={"quantity": adjustment.system_quantity, "updated_at": now},
    )
    previous_stock = inventory.quantity

    other_products_total = location_total_stock(adjustment.location, exclude_inventory_id=inventory.pk)
    projected_total = other_products_total + adjustment.physical_quantity
    if adjustment.location.capacity and projected_total > adjustment.location.capacity:
        raise AdjustmentRequestError(
            f"La ubicación {adjustment.location.code} no tiene capacidad suficiente "
            f"(máximo {adjustment.location.capacity}, proyectado {projected_total})."
        )

    inventory.quantity = adjustment.physical_quantity
    inventory.updated_at = now
    inventory.save(update_fields=["quantity", "updated_at"])

    InventoryTransaction.objects.create(
        product=adjustment.product,
        location=adjustment.location,
        user=supervisor_user,
        type="ajuste-aprobado",
        quantity=adjustment.delta,
        created_at=now,
    )

    InventoryAudit.objects.create(
        product=adjustment.product,
        location=adjustment.location,
        user=supervisor_user,
        movement_type=_movement_type_from_delta(adjustment.delta),
        quantity=abs(adjustment.delta),
        previous_stock=previous_stock,
        new_stock=inventory.quantity,
        observations=comment or "Ajuste aprobado",
    )

    adjustment.status = StockAdjustmentStatus.APPROVED
    adjustment.processed_by = supervisor_user
    adjustment.processed_at = now
    adjustment.resolution_comment = comment
    adjustment.save(
        update_fields=["status", "processed_by", "processed_at", "resolution_comment"]
    )
    return adjustment


@transaction.atomic
def reject_adjustment(
    adjustment_id: int,
    supervisor_user: Optional[User],
    comment: str = "",
) -> StockAdjustmentRequest:
    adjustment = StockAdjustmentRequest.objects.select_for_update().select_related(
        "product", "location"
    ).get(pk=adjustment_id)
    _validate_pending(adjustment)

    now = timezone.now()
    InventoryTransaction.objects.create(
        product=adjustment.product,
        location=adjustment.location,
        user=supervisor_user,
        type="ajuste-rechazado",
        quantity=0,
        created_at=now,
    )

    adjustment.status = StockAdjustmentStatus.REJECTED
    adjustment.processed_by = supervisor_user
    adjustment.processed_at = now
    adjustment.resolution_comment = comment
    adjustment.save(
        update_fields=["status", "processed_by", "processed_at", "resolution_comment"]
    )
    return adjustment


__all__ = [
    "AdjustmentRequestError",
    "create_adjustment_request",
    "list_adjustment_requests",
    "get_adjustment_request",
    "approve_adjustment",
    "reject_adjustment",
    "StockAdjustmentStatus",
    "get_adjustment_tolerance",
]
