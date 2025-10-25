"""Application services that expose the Product Factory to the rest of the app."""

from __future__ import annotations

from typing import Any, Dict

from django.db import transaction

from core.models import Product
from domain.factories.product_factory import ProductDraft, ProductFactory, ProductBlueprint

REQUIRED_FIELDS = ("sku", "name", "category")


def build_blueprint_from_payload(payload: Dict[str, Any]) -> ProductBlueprint:
    missing = [field for field in REQUIRED_FIELDS if not payload.get(field)]
    if missing:
        raise ValueError(f"Campos obligatorios faltantes: {', '.join(missing)}")

    try:
        reorder_point = int(payload.get("reorder_point", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("reorder_point debe ser numerico") from exc

    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise ValueError("metadata debe ser un objeto JSON")

    draft = ProductDraft(
        sku=str(payload["sku"]),
        name=str(payload["name"]),
        description=str(payload.get("description", "")),
        reorder_point=reorder_point,
        category=str(payload.get("category", "standard")).lower(),
        metadata=metadata,
    )
    return ProductFactory.build(draft)


@transaction.atomic
def persist_product_from_blueprint(blueprint: ProductBlueprint) -> Product:
    """Creates (or updates) a Product row based on a blueprint."""
    defaults = blueprint.to_model_kwargs()
    product, _ = Product.objects.update_or_create(sku=defaults.pop("sku"), defaults=defaults)
    return product


__all__ = ["build_blueprint_from_payload", "persist_product_from_blueprint"]
