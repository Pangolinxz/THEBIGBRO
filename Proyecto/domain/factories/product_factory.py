"""
Factory Method implementation that standardizes how different product species
are instantiated inside LogiTrace. Each blueprint encapsulates the domain rules
for a category (temperatura de almacenamiento, punto de reorden minimo, tags).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Type

from core.models import ProductCategory


@dataclass(slots=True)
class ProductDraft:
    sku: str
    name: str
    description: str = ""
    reorder_point: int = 0
    category: str = ProductCategory.STANDARD
    metadata: Dict[str, Any] = field(default_factory=dict)

    def normalized_category(self) -> str:
        candidate = (self.category or ProductCategory.STANDARD).lower()
        return candidate if candidate in ProductCategory.values else ProductCategory.STANDARD


class ProductBlueprint(ABC):
    """Product representation returned by the factory."""

    def __init__(self, draft: ProductDraft) -> None:
        self.draft = draft
        self.category = draft.normalized_category()

    def to_model_kwargs(self) -> Dict[str, Any]:
        """Serialize the blueprint to fields understood by Django's Product model."""
        return {
            "sku": self.draft.sku,
            "name": self.draft.name,
            "description": self.description(),
            "reorder_point": self.recommended_reorder_point(),
            "category": self.category,
        }

    def description(self) -> str:
        """Fills description with custom handling when blank."""
        return self.draft.description or self.storage_instructions()

    def summary(self) -> Dict[str, Any]:
        return {
            "sku": self.draft.sku,
            "name": self.draft.name,
            "category": self.category,
            "storage_instructions": self.storage_instructions(),
            "recommended_reorder_point": self.recommended_reorder_point(),
            "compliance_tags": self.compliance_tags(),
        }

    def recommended_reorder_point(self) -> int:
        return max(self.draft.reorder_point, self._minimum_reorder_point())

    def compliance_tags(self) -> List[str]:
        return []

    @abstractmethod
    def storage_instructions(self) -> str:
        ...

    @abstractmethod
    def _minimum_reorder_point(self) -> int:
        ...


class StandardProductBlueprint(ProductBlueprint):
    def storage_instructions(self) -> str:
        return "Almacenar en zona general, sin requisitos adicionales."

    def _minimum_reorder_point(self) -> int:
        return 5


class PerishableProductBlueprint(ProductBlueprint):
    def storage_instructions(self) -> str:
        temp = self.draft.metadata.get("temperature", "2-8C")
        return f"Mantener refrigerado entre {temp} y registrar fecha de caducidad."

    def compliance_tags(self) -> List[str]:
        return ["cold-chain", "expiry-tracking"]

    def _minimum_reorder_point(self) -> int:
        return 15


class FragileProductBlueprint(ProductBlueprint):
    def storage_instructions(self) -> str:
        return "Ubicar en racks superiores con senalizacion FRAGIL y doble verificacion de picking."

    def compliance_tags(self) -> List[str]:
        return ["fragile", "manual-handle"]

    def _minimum_reorder_point(self) -> int:
        return 8


class BulkProductBlueprint(ProductBlueprint):
    def storage_instructions(self) -> str:
        return "Asignar a zona de carga pesada, apilado maximo 2 pallets."

    def compliance_tags(self) -> List[str]:
        return ["bulk", "forklift-only"]

    def _minimum_reorder_point(self) -> int:
        return 20


class HazardousProductBlueprint(ProductBlueprint):
    def storage_instructions(self) -> str:
        return "Resguardar en area HAZMAT con ventilacion y registro MSDS disponible."

    def compliance_tags(self) -> List[str]:
        return ["hazmat", "ppe-required"]

    def _minimum_reorder_point(self) -> int:
        return 5


class ProductFactory:
    """Factory Method facade."""

    _registry: Dict[str, Type[ProductBlueprint]] = {
        ProductCategory.STANDARD: StandardProductBlueprint,
        ProductCategory.PERISHABLE: PerishableProductBlueprint,
        ProductCategory.FRAGILE: FragileProductBlueprint,
        ProductCategory.BULK: BulkProductBlueprint,
        ProductCategory.HAZARDOUS: HazardousProductBlueprint,
    }

    @classmethod
    def build(cls, draft: ProductDraft) -> ProductBlueprint:
        blueprint_cls = cls._registry.get(draft.normalized_category(), StandardProductBlueprint)
        return blueprint_cls(draft)


__all__ = [
    "ProductDraft",
    "ProductBlueprint",
    "ProductFactory",
    "StandardProductBlueprint",
    "PerishableProductBlueprint",
    "FragileProductBlueprint",
    "BulkProductBlueprint",
    "HazardousProductBlueprint",
]
