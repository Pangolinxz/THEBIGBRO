## 3. CU: Consultar Auditorías de Movimientos (RF_16)

### 3.1. Contexto actual

Este caso de uso implementa la consulta de los registros de auditoría generados por RF_14, RF_15 y otras operaciones del sistema. [cite_start]Provee trazabilidad sobre *qué* cambió, *cuándo* y *quién* lo hizo[cite: 12, 16].

* [cite_start]**Requisito:** RF_16 - Permitir al supervisor consultar registros de auditoría de movimientos con filtros[cite: 12].
* [cite_start]**Actores:** Supervisor de inventario, Sistema de gestión de inventario[cite: 9, 10].
* [cite_start]**Precondición:** Existen registros en `inventory_transaction`[cite: 18]. [cite_start]El usuario tiene rol de Supervisor[cite: 19].

### 3.2. Tareas de implementación

1.  **Modelos afectados**
    * [cite_start]`inventory_transaction` (o `audit_log`): Es la tabla principal de consulta[cite: 15, 27].
    * [cite_start]`user`, `product`, `location`: Se requiere hacer `JOIN` con estas tablas para mostrar información legible (nombres de usuario, producto y ubicación) en lugar de solo IDs [cite: 30, 32, 35][cite_start], tal como se ve en el mockup (USR, UBI, ID_P)[cite: 88, 92, 95].

2.  **Servicios (`domain/services/dashboard.py` o `auditing.py`)**
    * Se puede integrar este servicio en el `dashboard.py` (mencionado en `Guia_Casos_De_Uso.md`, sección 3) o crear un `auditing.py`.
    * **`get_audit_logs(filters)`**:
        * [cite_start]Debe aceptar un diccionario `filters` que contenga los criterios del Flujo Normal y del mockup[cite: 26, 78]:
            * [cite_start]`date_from` / `date_to` (Rango de fechas) [cite: 22, 80]
            * [cite_start]`user_id` (Usuario) [cite: 23, 81]
            * [cite_start]`action` (Acción) [cite: 24, 82]
            * [cite_start]`product_id` (Producto) [cite: 25, 83]
        * [cite_start]Debe construir una consulta (SQL vía Singleton o QuerySet) aplicando los filtros combinados[cite: 16, 27, 47].
        * [cite_start]Debe implementar la ordenación por Fecha o Usuario[cite: 37, 89].

3.  **Endpoints REST (API)**
    * [cite_start]El flujo inicia en "TRANSACCIONES" -> "Auditoría de movimientos"[cite: 73, 76, 78].
    * `GET /audit/movements/`
        * [cite_start]**Descripción:** Implementa la búsqueda[cite: 85]. Los filtros se pasarán como *query parameters*.
        * **Ejemplo:** `GET /audit/movements/?date_from=...&user_id=...&action=...`
        * [cite_start]**Respuesta:** Devuelve la tabla de resultados como se ve en el mockup[cite: 28, 87].
    * `GET /audit/movements/export/`
        * [cite_start]**Descripción:** Implementa la funcionalidad del botón "EXPORTAR"[cite: 38, 90, 97], permitiendo descargar los resultados filtrados (ej. CSV o PDF).

4.  **Autenticación y Roles**
    * El acceso a este módulo debe estar fuertemente restringido.
    * [cite_start]**Rol Requerido:** Supervisor (o superior)[cite: 19, 48].
    * Añadir decorador `# TODO auth`.