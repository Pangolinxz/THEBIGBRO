# Complementación pendiente – Autenticación y contraseñas (Tomas)

## 1. Contexto actual

- **Usuarios**: la tabla `user` ya existe (`username`, `full_name`, `email`, `role_id`). No hay hash de contraseña ni mecanismos de autenticación.
- **Roles**: `rol` contiene los perfiles (`Supervisor`, `Operador`, etc.). Los nuevos servicios (ajustes, futuros KPIs y alertas) asumen que el rol define permisos.
- **Endpoints sensibles**:
  - `/inventory/adjustments/` (`GET`, `POST`)
  - `/inventory/adjustments/<id>/` (`GET`, próximamente `PATCH`/`DELETE`)
  - CRUD genéricos bajo `/api/<modelo>/...`
  - `/products/factory/` y `/health/db/` (monitoreo)

Actualmente están abiertos para facilitar el desarrollo. Deben protegerse cuando la autenticación esté disponible.

## 2. Tareas que debe cubrir la implementación de login

1. **Modelo de credenciales**  
   - Agregar columnas `password_hash` (o similar) y `is_active` en `user`.  
   - Usar `hashlib`/`bcrypt`/`pbkdf2` o integrarse con `django.contrib.auth` mapeando nuestra tabla `user` a un `AbstractBaseUser`.

2. **Flujo de autenticación**  
   - Endpoint `POST /auth/login/` que reciba `username` + `password`, valide hash y devuelva token (JWT o sesión basada en cookie).  
   - Endpoint `POST /auth/logout/` (invalidar token o limpiar sesión).

3. **Decoradores/middleware**  
   - Decorador `@require_auth` o middleware que inyecte `request.user`.  
   - Permisos basados en rol (`@require_role("supervisor")`, etc.).  
   - Aplicar decoradores en:  
     - `adjustment_requests`, `adjustment_request_detail`  
     - `crud_collection`, `crud_resource`  
     - Futuras vistas de alertas/KPIs.

4. **Persistencia del token**  
   - Guardar token activo en tabla (opcional) o usar JWT firmado con `SECRET_KEY`.  
   - Definir expiración y renovación (refresh tokens si aplica).

5. **Pruebas**  
   - Tests unitarios para login correcto/incorrecto.  
   - Tests de autorización (HTTP 401/403 cuando falta token o rol).  
   - Actualizar colección Postman con ejemplos autenticados.

## 3. Integración con el trabajo entregado

- Los servicios de ajustes ya reciben `created_by`. Cuando el login esté listo, se debe pasar `request.user`.
- Endpoints que hoy retornan `TODO auth` deben reemplazarse por el decorador/configuración definida.
- Documentar en el README los roles disponibles y la forma de crear usuarios (comando `createsuperuser` o script SQL).
- Revisar `.env`: cuando se agregue JWT u otra solución, considerar variables `AUTH_TOKEN_TTL`, `PASSWORD_PEPPER`, etc. (cualquier cambio debe documentarse).

## 4. Recomendaciones

- Evaluar aprovechar `django.contrib.auth` para evitar reinventar hashing y manejo de usuarios; se puede crear un `CustomUser` que referencie `rol`.  
- Si opta por JWT, usar `djangorestframework-simplejwt` o librería similar; de lo contrario, implementar tokens firmados manualmente (clave en `.env`).  
- Mantener registro de auditoría (quién cerró alertas, aprobó ajustes) usando `request.user`.
- Acordar con el equipo cómo se realizará la migración de datos (usuarios actuales sin contraseña deberán resetearla).

> **Estado:** en espera de Tomas. El backend actual queda listo para conectar autenticación sin bloquear funcionalidades.
