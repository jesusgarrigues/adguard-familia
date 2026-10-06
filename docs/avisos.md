# Avisos

Avisos de bloqueos y solicitudes, Web Push y ajustes de perfil. Activación y diagnóstico detallados en [avisos-bloqueos.md](avisos-bloqueos.md). [Volver al README](../README.md).

## Avisos

El registro de consultas alimenta la actividad bloqueada y ofrece permisos temporales desde el evento. Los avisos requieren HTTPS y permiso. Al activar la suscripción Push en cada dispositivo, Docker puede enviarlos con Parental cerrada. La entrega local sin Push necesita el panel abierto. Los proveedores externos de correo/Telegram siguen pendientes.

Una consulta puede proceder de actividad en segundo plano. Se agrupan avisos por cliente y restricción cada 5 minutos, se leen las últimas 500 consultas cada 10 segundos y se guardan los últimos 500 eventos. Con mucho tráfico o desconexiones pueden perderse eventos. Un cliente excluido del registro no genera avisos. Para avisos de filtrado DNS se desactiva temporalmente el filtrado del cliente completo; no se crea una excepción solo para el dominio del aviso.

DNS no garantiza detener un vídeo o conexión ya abiertos al caducar: las cachés y conexiones persistentes pueden retrasarlo. DNS externo, VPN o DNS cifrado pueden evitar el filtro. El registro DNS no revela búsquedas individuales en páginas HTTPS.

## Perfiles, avisos y ajustes por integración

En **Ajustes → Parental → Mi perfil → Cambiar cara**, elige una cara y pulsa Guardar cara. Se conserva en el servidor y cambiar solo el avatar no cierra tus sesiones. El administrador también puede asignarlas en Usuarios y roles. Los dispositivos tienen doce ilustraciones originales a color, seleccionables desde su detalle; los servicios mantienen sus logos reconocibles y colores de marca.

**Ajustes → Integraciones** separa AdGuard Home (conexión, diagnóstico y configuración global de AdGuard) de Nintendo (cuenta y sincronización). Los ajustes de cada cliente o consola siguen en su popup.

Activar avisos muestra el estado del permiso, registra Push y presenta los errores en el mismo bloque. Probar aviso comprueba la entrega local; Probar desde el servidor comprueba el envío desde Docker, también con Parental cerrada. En iPhone/iPad: HTTPS, iOS/iPadOS 16.4 o posterior y Parental instalada en la pantalla de inicio. Los otros destinos externos y sus acciones interactivas #48/#50 siguen pendientes. [Detalles, fuentes y licencias de iconos](parental-perfiles-avisos-iconos.md).

La burbuja del icono instalado utiliza Badging API cuando esté disponible y cuenta las solicitudes pendientes visibles para tu cuenta; se elimina al cerrar sesión. En Android depende del navegador y launcher y puede estar ligada a los avisos activos. No se promete actualización con el panel cerrado. Al pulsar un aviso, se abre y enfoca la solicitud de aprobación concreta o el cliente y servicio bloqueados; las aprobaciones siguen siendo explícitas y autenticadas.

## Avisos selectivos de bloqueos

Configura servicios, protecciones opcionales e intervalos por responsable en Ajustes → Parental → Intentos bloqueados, con personalización por cliente. Al pulsar el aviso se abre la autorización del cliente/servicio concreto. [Guía y diagnóstico](avisos-bloqueos.md). Web Push entrega desde Docker con Parental cerrada; sin suscripción Push solo se entrega con el panel abierto. Los otros proveedores externos siguen pendientes.

Los avisos automáticos ahora usan una bandeja persistente y Web Push desde Docker. Tras actualizar, pulsa **Activar avisos** en cada dispositivo aunque ya tuviera permiso. **Probar desde el servidor** comprueba el canal con el panel cerrado; consulta [activación y diagnóstico](avisos-bloqueos.md).
