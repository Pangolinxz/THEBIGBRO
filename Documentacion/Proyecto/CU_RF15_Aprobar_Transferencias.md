## 2. CU: Aprobar o Rechazar Transferencias Internas (RF_15)

### 2.1. Contexto actual

Este caso de uso permite al supervisor validar el movimiento de inventario entre dos almacenes o bodegas internas (origen y destino).

* [cite_start]**Requisito:** RF_15 - Permitir al supervisor aprobar o rechazar transferencias internas[cite: 225].
* [cite_start]**Actores:** Supervisor de inventario, Sistema de gestión de inventario[cite: 222, 223].
* [cite_start]**Precondición:** Existe al menos una transferencia en estado "Pendiente de aprobación"[cite: 231]. [cite_start]El usuario tiene rol de Supervisor[cite: 232].

### 2.2. Tareas de implementación

1.  **Modelos afectados**
    * `InternalTransfer` (Modelo Nuevo): Se debe crear esta entidad (similar a `StockAdjustmentRequest`).
        * [cite_start]**Campos mínimos:** `product_id`, `quantity`, `origin_location_id` (almacén origen), `destination_location_id` (almacén destino), `motivo`, `status` ("Pendiente", "Aprobada", "Rechazada"), `created_by` (usuario solicitante)[cite: 237].
    * [cite_start]`inventory`: Si es **aprobada**, se debe actualizar el stock en *dos* ubicaciones: descuento en origen e incremento en destino[cite: 243]. [cite_start]Si es **rechazada**, no hay cambios en el inventario[cite: 246].
    * [cite_start]`inventory_transaction`: Se debe insertar un registro de auditoría para la trazabilidad en ambos casos[cite: 248, 249].

2.  **Servicios (`domain/services/transfers.py`)**
    * Se debe crear un nuevo servicio para esta lógica:
    * **`approve_transfer(transfer_id, supervisor_user)`**:
        * Valida que la transferencia `transfer_id` esté "Pendiente".
        * [cite_start]Ejecuta la doble transacción en `inventory` (resta en origen, suma en destino)[cite: 243].
        * [cite_start]Actualiza `InternalTransfer.status` = "Aprobada"[cite: 244].
        * [cite_start]Registra en `inventory_transaction`[cite: 248].
    * **`reject_transfer(transfer_id, supervisor_user, reason)`**:
        * Valida que la transferencia `transfer_id` esté "Pendiente".
        * [cite_start]Actualiza `InternalTransfer.status` = "Rechazada"[cite: 247].
        * [cite_start]Registra en `inventory_transaction`[cite: 248].

3.  **Endpoints REST (API)**
    * [cite_start]El flujo inicia en el menú "TRANSACCIONES" -> "Transferencias internas pendientes"[cite: 73, 234].
    * `GET /transfers/internal/pending/`
        * [cite_start]**Descripción:** Implementa los pasos 1 y 2 del Flujo Normal[cite: 234, 235]. Lista las transferencias pendientes.
    * `GET /transfers/internal/<id>/`
        * [cite_start]**Descripción:** Muestra el detalle de una transferencia para revisar (Producto, Cantidad, Origen, Destino, Motivo, Solicitante)[cite: 237, 301, 302, 303, 304, 305, 307].
    * `PATCH /transfers/internal/<id>/approve/`
        * [cite_start]**Descripción:** Ejecuta la acción "Aprobar transferencia"[cite: 240, 310]. Llama a `approve_transfer`.
    * `PATCH /transfers/internal/<id>/reject/`
        * [cite_start]**Descripción:** Ejecuta la acción "Rechazar transferencia"[cite: 241, 308]. Llama a `reject_transfer`.

4.  **Autenticación y Roles**
    * El acceso a todos estos endpoints debe estar restringido.
    * [cite_start]**Rol Requerido:** Supervisor[cite: 232].
    * Añadir decorador `# TODO auth`.