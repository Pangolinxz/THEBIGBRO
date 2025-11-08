## 1. CU: Aprobar o Rechazar Ajustes de Stock (RF_14)

### 1.1. Contexto actual

Este caso de uso es la continuación del **RF_13 (Conciliar conteo físico)**, que se describe en la `Guia_Casos_De_Uso.md` (sección 4). El RF_13 genera un registro en `StockAdjustmentRequest` con estado "PENDIENTE".

Este módulo (RF_14) implementa la lógica para que el Supervisor actúe sobre esa solicitud.

* [cite_start]**Requisito:** RF_14 - Permitir al supervisor aprobar o rechazar ajustes de stock[cite: 109].
* [cite_start]**Actores:** Supervisor de inventario, Sistema de gestión de inventario[cite: 106, 107].
* [cite_start]**Precondición:** Existe al menos un ajuste en estado "Pendiente de aprobación"[cite: 115]. [cite_start]El usuario tiene rol de Supervisor[cite: 116].

### 1.2. Tareas de implementación

1.  **Modelos afectados**
    * [cite_start]`StockAdjustmentRequest` (de RF_13): Se actualizará el campo `status` a "Aprobado" o "Rechazado"[cite: 127, 130].
    * [cite_start]`inventory`: Si la solicitud es **aprobada**, se debe actualizar el `quantity` en esta tabla según el `delta` del ajuste[cite: 126]. [cite_start]Si es **rechazada**, el stock no se modifica[cite: 129].
    * [cite_start]`inventory_transaction` (o `audit_log`): Se debe insertar un registro de auditoría en *ambos* casos (aprobado o rechazado) para cumplir con el registro de la acción[cite: 132, 140].

2.  **Servicios (`domain/services/adjustments.py`)**
    * El servicio definido en la guía (sección 4.2) debe contener la lógica de negocio:
    * **`approve_adjustment(adjustment_id, supervisor_user)`**:
        * Valida que el ajuste `adjustment_id` exista y esté en estado "PENDIENTE".
        * [cite_start]Actualiza el `inventory.quantity` con el valor físico (o `delta`)[cite: 126].
        * [cite_start]Actualiza `StockAdjustmentRequest.status` = "Aprobado"[cite: 127].
        * [cite_start]Registra la auditoría (quién, cuándo, qué) en `inventory_transaction`[cite: 132].
    * **`reject_adjustment(adjustment_id, supervisor_user, reason)`**:
        * Valida que el ajuste `adjustment_id` exista y esté "PENDIENTE".
        * [cite_start]Actualiza `StockAdjustmentRequest.status` = "Rechazado"[cite: 130].
        * [cite_start]Registra la auditoría en `inventory_transaction`[cite: 132].

3.  **Endpoints REST (API)**
    * Se implementarán los endpoints sugeridos en la `Guia_Casos_De_Uso.md` (sección 4.2) para que el Supervisor actúe:
    * `GET /inventory/adjustments/?status=PENDIENTE`
        * [cite_start]**Descripción:** Implementa los pasos 1 y 2 del Flujo Normal[cite: 118, 119]. Lista los ajustes que el Supervisor debe revisar.
    * `PATCH /inventory/adjustments/<id>/approve/`
        * [cite_start]**Descripción:** Ejecuta la acción de "Aprobar ajuste"[cite: 123]. Llama al servicio `approve_adjustment`.
    * `PATCH /inventory/adjustments/<id>/reject/`
        * [cite_start]**Descripción:** Ejecuta la acción de "Rechazar ajuste"[cite: 124]. Llama al servicio `reject_adjustment`.

4.  **Autenticación y Roles**
    * El acceso a todos estos endpoints debe estar restringido.
    * [cite_start]**Rol Requerido:** Supervisor[cite: 116].
    * Se debe añadir el decorador `# TODO auth` (mencionado en `Guia_Casos_De_Uso.md`, sección 5) hasta que la implementación de "Complementación Tomas" esté lista.