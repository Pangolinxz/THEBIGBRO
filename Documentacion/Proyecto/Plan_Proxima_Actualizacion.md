# Plan de Próxima Actualización (Frontend Django completo)

## 1. Objetivo

Construir la interfaz web completa dentro de Django para los casos de uso que ya funcionan en backend:

- RF06 / RF07 / RF08 – Ingresos, tablero inicial y movimientos básicos.  
- RF13 / RF14 – Solicitudes y aprobación de ajustes.  
- RF15 – Transferencias internas.  
- RF16 – Consulta / exportación de auditoría.  
- RF18 / RF19 – Alertas y tablero de indicadores (según guía).  
- Login/roles (implementado por Tomas) aplicado en toda la UI.

## 2. Herramientas y stack

- Django templates + vistas basadas en clases/funciones  
- Bootstrap 5 vía CDN (estilos rápidos)  
- `django.contrib.auth` (LoginView, LogoutView, permisos por rol)  
- `django.contrib.messages` para feedback  
- Servicios existentes en `domain/services` (adjustments, transfers, auditing, product factory, etc.)

## 3. Pasos detallados

### 3.1. Plantillas y layout
1. Crear `Proyecto/templates/base.html` con navbar (Dashboard, Ajustes, Transferencias, Auditoría, Alertas, Logout).  
2. Configurar `TEMPLATES[0]['DIRS'] = [BASE_DIR / "templates"]` y `STATICFILES_DIRS` si se agregan assets.  
3. Integrar bloques `{% block content %}` y mensajes flash (`{% if messages %}`).

### 3.2. Autenticación y roles
1. Reemplazar `login_view/logout_view` por `django.contrib.auth.views.LoginView/LogoutView` con plantillas en `templates/registration/`.  
2. Envolver vistas con `@login_required`.  
3. Añadir decorador `require_role("Supervisor")` y aplicarlo en Ajustes, Transferencias, Auditoría, Alertas.  
4. Mostrar en la UI el usuario logueado + botón “Cerrar sesión”.

### 3.3. Secciones UI
1. **Dashboard general (RF07/RF08/RF19)**  
   - Tarjetas con cifras rápidas (inventario total, ajustes pendientes, transferencias).  
   - Enlaces a cada módulo.  
   - Si es posible, gráficos simples (por ejemplo, movimientos por día usando Chart.js).
2. **Ingresos RF06**  
   - Formulario para registrar ingresos (usa `inventory_ingress`).  
   - Tabla con los últimos registros (consulta al endpoint o servicio).  
   - Mostrar validaciones y mensajes.
3. **Ajustes RF13/RF14**  
   - Lista de solicitudes (filtro por estado).  
   - Formulario para crear nuevos ajustes.  
   - Botones “aprobar” y “rechazar” que hagan POST a los servicios/URLs actuales.  
   - Mostrar `flagged`, `delta`, adjuntos.
4. **Transferencias RF15**  
   - Lista de transferencias pendientes y histórico.  
   - Formulario para crear nuevas transferencias internas (origen/destino).  
   - Botones “aprobar / rechazar” con comentarios.
5. **Auditoría RF16**  
   - Formulario de filtros (`date_from`, `date_to`, `user`, `producto`, `acción`).  
   - Tabla con resultados usando `get_audit_logs`.  
   - Botón “Exportar” que llama `/audit/movements/export/` y descarga CSV.  
   - Ordenación por fecha/usuario.
6. **Alertas RF18**  
   - Vista que consume el endpoint (por implementar) de alertas activas.  
   - Botón “Cerrar” por producto (PATCH).  
   - Mostrar déficit, ubicaciones, tiempo transcurrido.  
7. **Indicadores RF19**  
   - Mini dashboard con KPIs (rotación, fill rate, pedidos por estado).  
   - Reusar el servicio planificado en la guía (`dashboard.py`).

### 3.4. Navegación / UX
1. Breadcrumbs y mensajes flash (`messages.success/error`).  
2. Paginación (`django.core.paginator.Paginator`) en tablas largas.  
3. Uso de modales para ver detalle de un ajuste/transferencia si se desea.  
4. Botones/deshabilitados según estado (ej. no mostrar “aprobar” si ya está aprobado).

### 3.5. Seguridad
1. `@login_required` en todas las vistas (salvo login).  
2. `require_role("Supervisor")` en secciones críticas.  
3. `csrf_token` en todos los formularios.  
4. Evitar que los endpoints API queden abiertos (cuando Tomas conecte auth completa).  

### 3.6. Testing manual
1. Crear usuarios (operador / supervisor) y validar permisos.  
2. Flujos end-to-end:  
   - RF06: ingreso y ver reflejado en auditoría.  
   - RF13/RF14: crear ajuste, aprobar, auditar.  
   - RF15: crear transferencia, aprobar/rechazar, verificar inventario.  
   - RF16: aplicar filtros y exportar CSV.  
   - RF18: generar alerta (manual) y cerrarla.  
   - RF19: dashboard mostrando indicadores.  
3. Navegar el sitio completo sin Postman.

## 4. Resultados esperados

- Interface navegable que cubre RF06–RF19, reutilizando la lógica actual.  
- Supervisores pueden operar todo desde la web (sin Postman).  
- Autenticación y roles funcionando (aprovechando la implementación de Tomas).  
- Auditoría y exportaciones accesibles desde UI.  
- Base lista para demos y futura implementación del dashboard avanzado.
