from dataclasses import dataclass

ALLOWED_NOTIFICATION_TYPES = {
    "inventory_alert",
    "stockout",
    "capacity_warning",
    "dispatch_update",
}


@dataclass
class NotificationPayload:
    event_type: str
    message: str
    recipients: list

    def is_valid(self):
        if self.event_type not in ALLOWED_NOTIFICATION_TYPES:
            return False
        if not self.message:
            return False
        if not isinstance(self.recipients, list) or not self.recipients:
            return False
        return True


def validate_priority_tag(tag: str):
    allowed = {"low", "medium", "high"}
    if tag not in allowed:
        raise ValueError(f"Invalid priority tag: {tag}")


def calculate_fill_rate(delivered: int, ordered: int) -> float:
    if delivered < 0 or ordered <= 0:
        raise ValueError("Delivered and ordered must be positive values")

    fill_rate = (delivered / ordered) * 100
    return min(fill_rate, 100.0)
