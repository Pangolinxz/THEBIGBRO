import pytest
from datetime import datetime, timedelta


from domain.rules import (
    is_internal_email,
    require_fields,
    validate_dispatch_window,
    ALLOWED_NOTIFICATION_TYPES,
    NotificationPayload,
    calculate_fill_rate,
    validate_priority_tag,
    is_valid_reference_code,
    validate_capacity_projection,
    validate_order_status_transition
)

from core.models import OrderStatus


class TestBusinessRulesContacts:
    def test_validar_correo_operador_interno(self):
        assert is_internal_email("planner@logitrace.co")
        assert not is_internal_email("externo@gmail.com")

    def test_validar_campos_requeridos_producto(self):
        payload = {
            "sku": "SKU-001",
            "name": "Palet",
            "category": "standard",
            "reorder_point": 5,
        }
        require_fields(payload, ["sku", "name", "category"])
        with pytest.raises(ValueError):
            require_fields(payload, ["sku", "name", "description"])

    def test_validar_ventana_despacho(self):
        start = datetime(2024, 3, 10, 9, 0)
        end = start + timedelta(hours=3)
        validate_dispatch_window(start, end)
        with pytest.raises(ValueError):
            validate_dispatch_window(start, start)


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


class TestBusinessRulesOrders:
    def test_validar_transiciones_pedido(self):
        validate_order_status_transition(OrderStatus.CREATED, OrderStatus.RESERVED)
        validate_order_status_transition(OrderStatus.RESERVED, OrderStatus.DISPATCHED)
        with pytest.raises(ValueError):
            validate_order_status_transition(OrderStatus.CREATED, OrderStatus.DISPATCHED)

    def test_codigo_referencia_ubicacion(self):
        assert is_valid_reference_code("LOC-BX-0001")
        assert not is_valid_reference_code("loc-1")

    def test_validar_capacidad_proyectada(self):
        total = validate_capacity_projection(100, 70, 20, safety_margin=5)
        assert total == 95
        with pytest.raises(ValueError):
            validate_capacity_projection(80, 60, 30)
