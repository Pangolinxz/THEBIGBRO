# Guía de implementación – Casos de uso LogiTrace (borrador)

> **Nota:** Documento temporal para coordinar el desarrollo. Se eliminará una vez que el equipo haya repartido tareas y registrado las decisiones en la documentación oficial.

## 1. Estado actual del proyecto

- **Backend**: Django 5 con base MySQL accesible vía Singleton (`infrastructure/database.py`).  
- **API**: Endpoints REST genéricos `api/<modelo>/` para CRUD de tablas principales.  
- **Patrones**: Singleton operando en `/health/db/` y Factory Method para tipologías de producto (`/products/factory/`).  
- **Infraestructura**: `.env` controla las credenciales y el script `setup.bat` levanta venv + contenedor `db`. No se requieren ajustes para estos casos de uso.

## 2. CU: Ver y cerrar alertas activas

| Aspecto | Detalle |
| --- | --- |
| Requisito | RF_18 – Listar alertas activas y permitir cierre por producto. |
| Datos necesarios | `product`, `inventory` (sumatoria por producto), `product.reorder_point`, `stock_alert`. |
| Lógica clave | 1) Consolidar stock total × producto; 2) calcular déficit (`reorder_point - stock_total`); 3) ubicar códigos de `location` con cantidad > 0; 4) definir qué significa “alerta activa”. |

### 2.1. Requisitos previos

- Poblar `stock_alert` con al menos un registro por producto cuando se detecte déficit; conviene añadir un atributo `status` o `closed_at` para distinguir activas de cerradas (hoy solo tenemos `message`).  
- Asegurar integridad: `inventory.updated_at` debe tener datos reales para informar “tiempo transcurrido”.  
- Definir política de activación automática (trigger por cron o tarea manual).

### 2.2. Estrategia de implementación

1. **Consulta agregada (read)**  
   - Crear servicio en `domain/services/alerts.py` que use el Singleton para ejecutar SQL con `SUM(quantity)` por `product_id`.  
   - Combinar resultados con metadatos de `product` y filas en `stock_alert` sin cierre.
2. **Endpoint REST**  
   - Ruta `GET /alerts/` → devuelve lista de productos con alerta activa (SKU, nombre, mínimo, stock total, déficit, ubicaciones, triggered_at, minutos u horas transcurridos).  
   - `PATCH /alerts/<product_id>/close/` → inserta registro en `stock_alert` con `message='closed'` o actualiza la alerta existente (`status='CLOSED'`).  
3. **Actualizaciones al modelo**  
   - Si preferimos no alterar el schema, la acción de cierre se representará como una nueva fila con `message='closed @timestamp'`. De lo contrario, agregar campos `status`/`closed_at` (preferible a largo plazo).  
4. **UI (opcional)**  
   - Tabla en frontend con filtros y botón “Cerrar” que consuma los endpoints.

### 2.3. Requisitos implícitos

- Necesitamos un job o endpoint que genere las alertas cuando se detecte el déficit (actualmente no existe).  
- Control de roles: solo `Supervisor` debe poder cerrar alertas. Integrar cuando tengamos autenticación.  
- Registro de auditoría (quién cerró) requiere tabla/log adicional.

## 3. CU: Filtrar tablero de indicadores

| Aspecto | Detalle |
| --- | --- |
| Requisito | RF_20 – KPIs filtrables por producto/ubicación/rango de fechas. |
| Datos necesarios | `inventory`, `inventory_transaction`, `orders`, `order_item`. |
| Métricas sugeridas | Rotación de inventario, fill rate, días de inventario, pedidos por estado. |

### 3.1. Requisitos previos

- Garantizar que las tablas tengan suficiente data histórica (`created_at`, `updated_at`).  
- Determinar fórmula exacta de cada KPI (documentar en README/Confluence).  
- Preparar funciones de agregación optimizadas (posible uso de vistas SQL).  
- Asegurar que `inventory_transaction` registre tipo (entrada/salida) para calcular rotación.

### 3.2. Estrategia de implementación

1. **Servicio de KPIs** (`domain/services/dashboard.py`)  
   - Recibe filtros (`product_sku`, `location_code`, `date_from`, `date_to`).  
   - Usa consultas SQL (Singleton) o QuerySets predefinidos para calcular cada métrica.  
   - Maneja casos “sin datos”.
2. **Endpoint**  
   - `GET /dashboard/kpis/?product=SKU-1&location=LOC-1&from=2025-01-01&to=2025-02-01`.  
   - Respuesta JSON con KPIs + metadatos (filtros aplicados, totales, etc.).  
   - Registrar en logs la acción (usuario + filtros) para trazabilidad.
3. **Frontend (futuro)**  
   - Componentes de selección (auto-complete para productos/ubicaciones) que consuman los endpoints `GET /api/products/` y `GET /api/locations/`.  
   - Visualización (gráficas o cards).
4. **Performance**  
   - Si la consulta empieza a tardar >2 s, evaluar cache local (Python) o materializar agregados (tabla summary).

### 3.3. Requisitos implícitos

- Listado de usuarios por rol (para restringir acceso a Supervisores).  
- Mecanismo de exportación (CSV/PDF) si se decide implementar la nota opcional.  
- Logs centralizados (puede ser Django logging + tabla `audit_log`).

## 4. CU: Conciliar conteo físico vs sistema

| Aspecto | Detalle |
| --- | --- |
| Requisito | RF_13 – Operador crea solicitud de ajuste, Supervisor la revisa (PENDIENTE). |
| Resultado esperado | Se registra la solicitud; el ajuste se aplica en flujo aparte (aprobación). No se modifica `inventory` en este caso. |

### 4.1. Requisitos previos

- Definir nueva entidad: `stock_adjustment_request` con campos mínimos: `id`, `product_id`, `location_id`, `system_qty`, `physical_qty`, `delta`, `reason`, `attachment_url`, `status`, `created_by`, `created_at`.  
- Normalizar persistencia de adjuntos (carpeta/local storage/S3).  
- Establecer tolerancia (`abs(delta) <= threshold`) configurable (tabla `config` o `.env`).

### 4.2. Estrategia de implementación

1. **Modelo + migración** para `StockAdjustmentRequest`.  
2. **Servicio de conciliación** (`domain/services/adjustments.py`)  
   - Calcula `delta`, marca si excede tolerancia.  
   - Valida SKU y location (ya podemos reutilizar endpoints de productos/ubicaciones).  
   - Insert en estado `PENDIENTE`.  
   - Opcional: enviar notificación (email/log) a Supervisor.
3. **Endpoints**  
   - `POST /inventory/adjustments/` (Operador) → crea solicitud.  
   - `GET /inventory/adjustments/?status=PENDIENTE` (Supervisor) → lista pendientes.  
   - `PATCH /inventory/adjustments/<id>/approve|reject` → se implementará junto al RF_14 (aplicación del ajuste).  
4. **UI**  
   - Formulario en frontend que consuma `/api/products/` y `/api/locations/` para autocompletar.  
   - Vista del Supervisor con filtros por estado/fecha/SKU.

### 4.3. Requisitos implícitos

- Control de roles (solo Operador crea, Supervisor aprueba).  
- Gestión de adjuntos (puede ser ruta en file system).  
- Méritos de auditoría (quién aprobó/rechazó).

## 5. Autenticación y roles pendientes (“Complementación Tomas”)

- El sistema hoy no tiene login ni manejo de contraseñas.  
- Para no bloquear el avance:
  - **Endpoints actuales**: documentar que requieren autenticación futura (añadir decorator placeholder, p. ej. `# TODO: require_login`).  
  - **Diseño propuesto**: Django `User` + `Rol` (ya existe tabla `rol`). Tomas puede implementar:
    1. Middleware o decorador que lea tokens/cookies.
    2. Tabla `user` ya está en modelos; falta hash de contraseña y flujo de login.
    3. Permisos: `Supervisor` con acceso completo; `Operador` restringido al CRUD relevante.  
  - **Preparación nuestra**: en cada endpoint crítico dejar comentarios `# TODO auth` y, cuando se registre en README, especificar qué roles deberían acceder.  
- **Pruebas**: mientras no haya auth, utilizamos el sistema en modo abierto (ideal para desarrollo). Antes de liberar, Tomas añadirá autenticación y revisaremos tests.

## 6. Backlog sugerido

1. Automatizar generación de alertas (job o trigger manual).  
2. Implementar endpoints `/alerts/` (GET) y `/alerts/<id>/close/` (PATCH).  
3. Diseñar servicio de KPIs con filtros y endpoint `/dashboard/kpis/`.  
4. Definir modelo `StockAdjustmentRequest` y endpoints para solicitudes.  
5. Incorporar autenticación (Tomas) y ajustar permisos en endpoints existentes.  
6. Añadir pruebas unitarias + Postman collection para los CU.  
7. Documentar comandos de reinicio de `AUTO_INCREMENT` solo para ambientes locales (apéndice opcional).  
8. Explorar frontend (tableros y secciones) después de confirmar API.

## 7. Impacto en archivos sensibles

- **`.env`**: sin cambios requeridos para estos casos.  
- **`setup.bat`**: no requiere ajuste (sigue levantando base y servidor).  
- **`requirements.txt`**: ya incluye `cryptography` para PyMySQL; no se prevén dependencias extra.

---

> El equipo puede utilizar este documento como checklist. Una vez que se asignen tareas y se registren decisiones oficiales en la documentación del proyecto, eliminaremos este archivo temporal.
