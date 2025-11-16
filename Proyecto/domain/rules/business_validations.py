from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Sequence, Set

from core.models import OrderStatus

WAREHOUSE_EMAIL_DOMAIN = "logitrace.co"
ALLOWED_ROLES: Set[str] = {"coordinator", "picker", "planner"}
ALLOWED_NOTIFICATION_TYPES: Set[str] = {
    "inventory_alert",
    "dispatch_created",
    "order_delay",
}
ORDER_STATUS_TRANSITIONS = {
    OrderStatus.CREATED: {OrderStatus.RESERVED, OrderStatus.CLOSED},
    OrderStatus.RESERVED: {OrderStatus.DISPATCHED, OrderStatus.CREATED},
    OrderStatus.DISPATCHED: {OrderStatus.CLOSED},
    OrderStatus.CLOSED: set(),
}
PRIORITY_TAGS = {"low", "medium", "high"}
REFERENCE_PATTERN = re.compile(r"^[A-Z]{3}-[A-Z]{2}-\d{4}$")


def is_internal_email(email: str, domain: str = WAREHOUSE_EMAIL_DOMAIN) -> bool:
    return bool(email) and email.lower().endswith(f"@{domain}")


def require_fields(data: dict, required_fields: Sequence[str]) -> None:
    missing = [field for field in required_fields if not str(data.get(field, "")).strip()]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")


def validate_dispatch_window(start: datetime, end: datetime) -> None:
    if end <= start:
        raise ValueError("dispatch window end must be after start")


def validate_positive_quantity(value: int) -> None:
    if value <= 0:
        raise ValueError("quantity must be positive")


def sanitize_comment(comment: str) -> str:
    return re.sub(r"\s+", " ", comment or "").strip()


def validate_role(role: str) -> None:
    if role not in ALLOWED_ROLES:
        raise ValueError("role not allowed")


def validate_order_status_transition(current: str, target: str) -> None:
    allowed = ORDER_STATUS_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(f"transition {current}->{target} is forbidden")


def is_valid_reference_code(code: str) -> bool:
    return bool(code and REFERENCE_PATTERN.match(code))


def validate_capacity_projection(
    capacity: int,
    current_load: int,
    incoming: int,
    safety_margin: int = 0,
) -> int:
    projected = current_load + incoming + safety_margin
    if projected > capacity:
        raise ValueError("capacity exceeded")
    return projected


def validate_priority_tag(priority: str) -> None:
    if priority not in PRIORITY_TAGS:
        raise ValueError("invalid priority tag")


def calculate_fill_rate(served: int, requested: int) -> float:
    if requested <= 0:
        raise ValueError("requested must be positive")
    if served < 0:
        raise ValueError("served cannot be negative")
    return round(min(served / requested, 1) * 100, 1)


@dataclass
class NotificationPayload:
    event_type: str
    message: str
    recipients: List[int] = field(default_factory=list)

    def is_valid(self) -> bool:
        return (
            self.event_type in ALLOWED_NOTIFICATION_TYPES
            and bool(self.message.strip())
            and all(isinstance(r, int) and r > 0 for r in self.recipients)
        )


__all__ = [
    "ALLOWED_NOTIFICATION_TYPES",
    "ALLOWED_ROLES",
    "NotificationPayload",
    "ORDER_STATUS_TRANSITIONS",
    "calculate_fill_rate",
    "is_internal_email",
    "is_valid_reference_code",
    "require_fields",
    "sanitize_comment",
    "validate_capacity_projection",
    "validate_dispatch_window",
    "validate_order_status_transition",
    "validate_priority_tag",
    "validate_positive_quantity",
    "validate_role",
]
