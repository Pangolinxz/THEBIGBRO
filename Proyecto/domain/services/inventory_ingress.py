"""Services to handle product ingress (RF_6)."""

from __future__ import annotations

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
    User,
)


class IngressError(ValueError):
    """Raised when the ingress payload is invalid."""


@dataclass(frozen=True)
class IngressResult:
    audit: InventoryAudit
    transaction: InventoryTransaction
    inventory: Inventory


def _parse_positive_int(value, field: str) -> int:
    try:
        qty = int(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise IngressError(f"{field} debe ser un entero positivo") from exc
    if qty <= 0:
        raise IngressError(f"{field} debe ser mayor que cero")
    return qty


def _get_product(sku: str) -> Product:
    try:
        return Product.objects.get(sku=sku)
    except Product.DoesNotExist as exc:
        raise IngressError(f"Producto con SKU '{sku}' no existe") from exc


def _get_location(code: str) -> Location:
    try:
        return Location.objects.get(code=code)
    except Location.DoesNotExist as exc:
        raise IngressError(f"Ubicacion con codigo '{code}' no existe") from exc


@transaction.atomic
def register_product_ingress(
    payload: Dict[str, object],
    created_by: Optional[User] = None,
) -> IngressResult:
    sku = str(payload.get("sku", "")).strip()
    location_code = str(payload.get("location_code", "")).strip()
    observations = str(payload.get("observations") or "").strip()

    if not sku:
        raise IngressError("Debe proporcionar el SKU del producto")
    if not location_code:
        raise IngressError("Debe proporcionar el codigo de ubicacion")

    quantity = _parse_positive_int(payload.get("quantity"), "quantity")

    product = _get_product(sku)
    location = _get_location(location_code)

    now = timezone.now()

    inventory, _ = Inventory.objects.select_for_update().get_or_create(
        product=product,
        location=location,
        defaults={"quantity": 0, "updated_at": now},
    )
    previous_stock = inventory.quantity
    new_stock = previous_stock + quantity

    inventory.quantity = new_stock
    inventory.updated_at = now
    inventory.save(update_fields=["quantity", "updated_at"])

    transaction_record = InventoryTransaction.objects.create(
        product=product,
        location=location,
        user=created_by,
        type="ingreso",
        quantity=quantity,
        created_at=now,
    )

    audit = InventoryAudit.objects.create(
        product=product,
        location=location,
        user=created_by,
        movement_type=InventoryAudit.MOVEMENT_INGRESS,
        quantity=quantity,
        previous_stock=previous_stock,
        new_stock=new_stock,
        observations=observations,
    )

    return IngressResult(audit=audit, transaction=transaction_record, inventory=inventory)


def list_ingress_records(limit: int = 50):
    qs = (
        InventoryAudit.objects.select_related("product", "location", "user")
        .filter(movement_type=InventoryAudit.MOVEMENT_INGRESS)
        .order_by("-created_at")
    )
    if limit:
        qs = qs[:limit]
    return list(qs)


__all__ = ["IngressError", "register_product_ingress", "list_ingress_records", "IngressResult"]
