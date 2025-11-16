# Testing Unitario – RF08 / Inventario

> **Nota:** reemplaza los placeholders de imágenes (`figX.png`) por las capturas reales antes de convertir a PDF. Mantén tipografía Arial 11 (o el formato IEEE/APA que prefieras) siguiendo las pautas del profesor.

---

## 1. Contexto

- **Proyecto:** LogiTrace – WMS académico  
- **Módulo:** Testing (RF-08, RF-06, regla de capacidad)  
- **Integrantes:** (añadir nombres y roles)  
- **Herramienta:** `pytest` + `pytest-django`
- **Configuración:** `pytest.ini` establece `DJANGO_SETTINGS_MODULE=logitrace.settings` y `tests/conftest.py` fuerza uso de SQLite en memoria para no depender de MySQL.

## 2. Casos verificados ✅

| # | Test | Objetivo | Resultado esperado |
|---|------|----------|--------------------|
| 1 | `test_reserve_order_marks_items_and_status` | Verificar que `reserve_order` cambie el estado del pedido a `RESERVED` y marque los ítems como reservados cuando hay stock suficiente. | Pedido pasa a `RESERVED`; cada `OrderItem.reserved` queda en `True`. |
| 2 | `test_dispatch_order_updates_inventory_and_creates_movements` | Confirmar que el despacho descuente inventario, genere transacciones/auditorías y marque el pedido como `DISPATCHED`. | Inventario disminuye exactamente la cantidad despachada; existen registros en `InventoryTransaction` (type `order-dispatch`) y `InventoryAudit` (egreso). |
| 3 | `test_register_product_ingress_blocks_capacity_overflow` | Validar que `register_product_ingress` bloquee ingresos que exceden la capacidad declarada de la ubicación. | Se lanza `IngressError` cuando `cantidad > capacity`. |

> Emoji sugerido para resaltar: ✅ o ⚠️ (no abusar).

## 3. Ejecución de pruebas

1. Activar entorno virtual: `.\.venv\Scripts\activate`
2. Instalar dependencias: `pip install -r requirements.txt`
3. Ejecutar: `python -m pytest`

### Evidencia (ANTES)

![Salida Pytest – antes](fig1_pytest_run.png)

### Evidencia (DESPUÉS)

![Salida Pytest – éxito](fig2_pytest_success.png)

Describe brevemente que la ejecución final muestra `3 passed` en ~1.8s gracias al backend SQLite en memoria.

## 4. Casos límites / Análisis

- **Reserva sin stock**: si no hay inventario en la ubicación, `reserve_order` lanza `OrderDispatchError`. Esto se probó manualmente (menciona la captura si aplica) o explica por qué la prueba actual cubre el camino positivo y se documentó el negativo en los casos de uso.
- **Despacho incompleto**: cuando faltan ítems o la ubicación no existe, el test fallaría, garantizando que no se descuente stock inexistente.
- **Ingreso fuera de capacidad**: `IngressError` protege la integridad física de las bodegas; el test asegura que la validación se ejecuta antes de crear registros.

## 5. Conclusiones 🎯

- Se automatizaron tres pruebas críticas con `pytest`, demostrando que los servicios de reserva, despacho e ingresos respetan las reglas de negocio.
- El entorno de pruebas es reproducible (SQLite en memoria, sin dependencias externas).
- Las evidencias adjuntas muestran ejecución exitosa; cualquier contribución futura debe mantener estos tests verdes antes de fusionar cambios.

## 6. Referencias

- `Proyecto/tests/test_orders.py`
- `Proyecto/tests/test_inventory_ingress.py`
- `pytest.ini`, `requirements.txt`

---

> Una vez completes con datos reales y pegues las capturas, exporta este archivo a PDF y colócalo en `Documentacion/Proyecto/testing_utest.pdf`.
