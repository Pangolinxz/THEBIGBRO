"""Domain services for internal transfers (RF_15)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from django.db import transaction
from django.utils import timezone

from core.models import (
    InternalTransfer,
    TransferStatus,
    Inventory,
    InventoryTransaction,
    InventoryAudit,
    Product,
    Location,
    User,
)


class TransferRequestError(ValueError):
    """Raised when an internal transfer has invalid data or state."""


def _get_transfer(pk: int) -> InternalTransfer:
    return InternalTransfer.objects.select_related(
        "product",
        "origin_location",
        "destination_location",
        "created_by",
        "processed_by",
    ).get(pk=pk)


def list_internal_transfers(filters: Optional[Dict[str, str]] = None):
    qs = InternalTransfer.objects.select_related(
        "product",
        "origin_location",
        "destination_location",
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
    origin_code = (filters.get("origin") or "").strip()
    if origin_code:
        qs = qs.filter(origin_location__code__iexact=origin_code)
    destination_code = (filters.get("destination") or "").strip()
    if destination_code:
        qs = qs.filter(destination_location__code__iexact=destination_code)
    return qs


def get_internal_transfer(pk: int) -> InternalTransfer:
    return _get_transfer(pk)


def _validate_pending(transfer: InternalTransfer):
    if transfer.status != TransferStatus.PENDING:
        raise TransferRequestError("La transferencia ya fue procesada.")
    if transfer.origin_location_id == transfer.destination_location_id:
        raise TransferRequestError("La transferencia debe tener origen y destino diferentes.")
    if transfer.quantity <= 0:
        raise TransferRequestError("La cantidad debe ser mayor que cero.")


@transaction.atomic
def approve_transfer(
    transfer_id: int,
    supervisor_user: Optional[User],
    comment: str = "",
) -> InternalTransfer:
    transfer = InternalTransfer.objects.select_for_update().select_related(
        "product",
        "origin_location",
        "destination_location",
    ).get(pk=transfer_id)
    _validate_pending(transfer)

    now = timezone.now()
    product = transfer.product
    origin = transfer.origin_location
    destination = transfer.destination_location
    qty = transfer.quantity

    origin_inventory = (
        Inventory.objects.select_for_update()
        .filter(product=product, location=origin)
        .first()
    )
    if origin_inventory is None or origin_inventory.quantity < qty:
        raise TransferRequestError("Inventario insuficiente en el origen.")

    destination_inventory, _ = Inventory.objects.select_for_update().get_or_create(
        product=product,
        location=destination,
        defaults={"quantity": 0, "updated_at": now},
    )

    origin_previous = origin_inventory.quantity
    destination_previous = destination_inventory.quantity

    origin_inventory.quantity = origin_previous - qty
    origin_inventory.updated_at = now
    origin_inventory.save(update_fields=["quantity", "updated_at"])

    destination_inventory.quantity = destination_previous + qty
    destination_inventory.updated_at = now
    destination_inventory.save(update_fields=["quantity", "updated_at"])

    InventoryTransaction.objects.bulk_create(
        [
            InventoryTransaction(
                product=product,
                location=origin,
                user=supervisor_user,
                type="transfer-egress",
                quantity=qty,
                created_at=now,
            ),
            InventoryTransaction(
                product=product,
                location=destination,
                user=supervisor_user,
                type="transfer-ingress",
                quantity=qty,
                created_at=now,
            ),
        ]
    )

    InventoryAudit.objects.create(
        product=product,
        location=origin,
        user=supervisor_user,
        movement_type=InventoryAudit.MOVEMENT_EGRESS,
        quantity=qty,
        previous_stock=origin_previous,
        new_stock=origin_inventory.quantity,
        observations=comment or "Transferencia aprobada (origen)",
    )

    InventoryAudit.objects.create(
        product=product,
        location=destination,
        user=supervisor_user,
        movement_type=InventoryAudit.MOVEMENT_INGRESS,
        quantity=qty,
        previous_stock=destination_previous,
        new_stock=destination_inventory.quantity,
        observations=comment or "Transferencia aprobada (destino)",
    )

    transfer.status = TransferStatus.APPROVED
    transfer.processed_by = supervisor_user
    transfer.processed_at = now
    transfer.resolution_comment = comment
    transfer.save(
        update_fields=["status", "processed_by", "processed_at", "resolution_comment"]
    )
    return transfer


@transaction.atomic
def reject_transfer(
    transfer_id: int,
    supervisor_user: Optional[User],
    comment: str,
) -> InternalTransfer:
    transfer = InternalTransfer.objects.select_for_update().get(pk=transfer_id)
    _validate_pending(transfer)
    if not comment:
        raise TransferRequestError("Debe proporcionar un motivo para rechazar.")

    now = timezone.now()
    InventoryTransaction.objects.create(
        product=transfer.product,
        location=transfer.origin_location,
        user=supervisor_user,
        type="transfer-rejected",
        quantity=0,
        created_at=now,
    )

    transfer.status = TransferStatus.REJECTED
    transfer.processed_by = supervisor_user
    transfer.processed_at = now
    transfer.resolution_comment = comment
    transfer.save(
        update_fields=["status", "processed_by", "processed_at", "resolution_comment"]
    )
    return transfer


__all__ = [
    "TransferRequestError",
    "list_internal_transfers",
    "get_internal_transfer",
    "approve_transfer",
    "reject_transfer",
]
