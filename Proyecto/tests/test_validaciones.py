import pytest

from domain.rules import (
    ALLOWED_NOTIFICATION_TYPES,
    NotificationPayload,
    calculate_fill_rate,
    validate_priority_tag,
)


class TestBusinessRulesNotifications:
    def test_prioridades_envio(self):
        validate_priority_tag("low")
        validate_priority_tag("high")
        with pytest.raises(ValueError):
            validate_priority_tag("urgent")

    def test_notificacion_valida(self):
        payload = NotificationPayload(
            event_type="inventory_alert",
            message="Ubicación LOC-A supera el 95% de ocupación",
            recipients=[1, 2],
        )
        assert payload.is_valid()
        assert "inventory_alert" in ALLOWED_NOTIFICATION_TYPES

    def test_calculo_fill_rate(self):
        assert calculate_fill_rate(8, 10) == 80.0
        assert calculate_fill_rate(12, 10) == 100.0
        with pytest.raises(ValueError):
            calculate_fill_rate(0, 0)