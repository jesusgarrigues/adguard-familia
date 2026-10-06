# Usuarios, roles y solicitudes

[Volver al README](../README.md).

Al actualizar se conservan los clientes, la conexión y los permisos. La primera entrada pide APP_TOKEN para crear un administrador con usuario y contraseña (mínimo 12 caracteres). Una vez creado, APP_TOKEN deja de autorizar la API; todas las personas entran con su cuenta.

En **Usuarios**, el administrador crea cuentas y asigna clientes:

| Rol | Acceso |
| --- | --- |
| Administrador | Usuarios, servidor, ajustes globales, todos los clientes, permisos y auditoría. |
| Responsable | Aprobar/rechazar solicitudes y conceder/cancelar permisos en clientes asignados. Edición permanente solo si se activa expresamente. |
| Solicitante | Restricciones y permisos de clientes asignados; solicitar acceso y retirar sus solicitudes pendientes. Nunca desbloquea por su cuenta. No ve historial DNS. |
| Observador | Consulta de dispositivos asignados, actividad y permisos; sin cambios ni aprobaciones. |

Los límites de aprobación se configuran por cuenta responsable. No hay cupos automáticos ni autoaprobación. Las solicitudes caducan a las 24 horas; el permiso comienza al concederse y cada ampliación necesita aprobación. La pantalla **Solicitudes** permite al responsable ajustar los minutos y decidir. Un error de aplicación se muestra para revisar los permisos antes de reintentar. **Registro** conserva los últimos 5000 accesos/cambios/aprobaciones. No registra contraseñas.

Las contraseñas se guardan con scrypt y sal individual. Las sesiones usan cookies HttpOnly, SameSite=Strict y caducan a las 12 horas. Al modificar una cuenta se cierran sus sesiones. El rol, la asignación y el límite se verifican en el servidor; ocultar botones no es la autorización. Los POST autenticados verifican un token CSRF. El proxy HTTPS debe enviar `X-Forwarded-Proto: https` para marcar la cookie Secure.
