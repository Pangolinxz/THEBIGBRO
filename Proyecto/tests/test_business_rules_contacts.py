import pytest
from datetime import datetime, timedelta

from domain.rules import is_internal_email, require_fields, validate_dispatch_window


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
