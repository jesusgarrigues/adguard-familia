# Avisos de servicios bloqueados

En **Ajustes → Parental → Intentos bloqueados**, cada administrador o responsable configura sus propios avisos:

- **Todos los servicios bloqueados**, **Solo los servicios seleccionados** o **Ningún servicio**.
- Catálogo obtenido de AdGuard, agrupado y con búsqueda.
- Una selección general y personalización por cliente. Al volver a usar la general se elimina la personalización de avisos, sin tocar AdGuard.
- Otros bloqueos opcionales: filtrado DNS, control parental, navegación segura y búsqueda segura. Están desactivados por defecto para reducir ruido.
- Intervalo mínimo de 5 a 1440 minutos entre avisos del mismo cliente y servicio. Las solicitudes explícitas de tiempo siguen teniendo sus avisos independientes.

Las preferencias se guardan en el volumen de datos, por usuario. No cambian restricciones ni borran Actividad. Las cuentas con acceso limitado solo ven sus clientes. Cambiar preferencias no reenvía el historial. Los avisos iniciales de servicios están activados; sigue siendo necesario conceder permiso al navegador.

## Desde un aviso

Una notificación de bloqueo abre un diálogo específico, por ejemplo **Permitir YouTube → Televisiones**, con la consulta, fecha y selección de minutos. Un responsable confirma dentro de sus límites; un solicitante solo envía una solicitud; un observador consulta. El enlace nunca concede acceso por sí mismo ni crea solicitudes a partir de actividad en segundo plano.

El servidor comprueba de nuevo cliente, rol, duración, bloqueo actual y ausencia de un permiso ya activo al confirmar desde el diálogo. Un cambio de configuración o una concesión de otro responsable se informa como error. Las restricciones se restauran al caducar. Si el aviso exige iniciar sesión, se conserva el destino tanto en acceso local como en Authentik.

## Detección y diagnóstico

Parental consulta el registro de AdGuard cada 10 segundos y reconoce `FilteredBlockedService` con su `service_name`. La búsqueda segura se identifica mediante `FilteredSafeSearch`. Los bloqueos genéricos de listas siguen siendo Filtrado DNS: no se convierten en YouTube por reconocer un dominio.

Se relacionan clientes por nombre registrado, ClientID, IP exacta y CIDR; ante CIDR superpuestos se elige el más específico. Los registros duplicados y ráfagas del mismo cliente/servicio se agrupan en intervalos de 5 minutos, antes de aplicar el intervalo elegido por cada receptor. Se usa la hora original de consulta. Los registros antiguos se muestran como actividad, sin generar notificaciones nuevas.

En **Ajustes → Integraciones → AdGuard Home → Conexión → Diagnóstico** se informa la última lectura, número de consultas, motivos recibidos, registros reconocidos, incidencias de formato y clientes excluidos. Si la ventana de 500 consultas se llena, se señala que con mucho tráfico podrían faltar consultas entre lecturas.

Si no aparece un intento, comprueba en el registro de AdGuard que la consulta llega desde ese dispositivo y que el cliente no está excluido del registro. Caché DNS, otro resolutor o DNS cifrado pueden impedir nuevas consultas visibles en AdGuard. Una consulta no demuestra que alguien estuviera viendo contenido.

## Entrega automática y diagnóstico

Los avisos nuevos elegibles se guardan en una bandeja por usuario en el servidor. Actividad conserva el registro DNS completo; Avisos contiene los intentos seleccionados por preferencias. Las solicitudes tienen su propio contador. Una consulta repetida no crea una solicitud ni aumenta continuamente el contador.

La ventana de 120 segundos se usa al **recoger una consulta nueva de AdGuard**, no para borrar un aviso ya pendiente. Después de recogerlo se conserva en la bandeja durante 30 días, hasta leerlo. No se importan todos los eventos históricos al actualizar. Los envíos pendientes se intentan durante una hora y tienen un máximo de cinco intentos con espera creciente; leer el aviso, resolver su solicitud o cambiar su ámbito cancela el envío. Recibir un aviso nunca concede un permiso.

El contador de Avisos muestra bloqueos no leídos. El icono instalado suma ese número y las solicitudes pendientes, cuando el sistema permite Badging API. Leer una solicitud no la resuelve y no reduce su contador de pendientes. Al pulsar un aviso se abre su autorización o solicitud concreta; la sesión y los roles siguen siendo obligatorios. Marcar todos como leídos no aprueba nada. Otros dispositivos actualizan su contador al volver a abrir o recibir un nuevo Push; no se envía Push silencioso solo para cambiar números.

### Activar el envío desde Docker

1. Actualiza el contenedor y abre Parental mediante HTTPS. En iPhone usa la app añadida a pantalla de inicio (iOS 16.4 o posterior).
2. En Ajustes → Parental → Avisos del navegador, pulsa **Activar avisos**, incluso si ya diste permiso en una versión anterior. Ahora registra la suscripción Push de este dispositivo.
3. **Probar aviso** comprueba la entrega local del navegador. **Probar desde el servidor** pone un mensaje en la cola de Docker con unos 10 segundos de espera: puedes poner Parental en segundo plano para verificarlo.
4. Consulta el estado de envío en ese mismo bloque. «Aceptado» significa que el navegador/proveedor aceptó el mensaje; el sistema puede agruparlo o silenciarlo por sus ajustes de notificaciones/concentración.

El servidor envía Web Push cifrado con VAPID mediante Apple, Google o Mozilla; no hace falta una app nativa propia ni cuenta de desarrollador Apple. El contenedor necesita acceso HTTPS saliente a `web.push.apple.com`, `fcm.googleapis.com` o `updates.push.services.mozilla.com`, según el navegador. Si un firewall bloquea esas conexiones se informa el fallo y se reintenta. No se aceptan URLs Push arbitrarias o de la red privada y no se siguen redirecciones.

La clave privada se genera una sola vez en `/data/web-push.pem` con permisos 0600. Conserva el volumen de datos para mantener suscripciones, cuentas y avisos. Opcionalmente configura `WEB_PUSH_CONTACT=mailto:tu-correo@tu-dominio` como contacto VAPID en el entorno del contenedor. No compartas la clave privada ni los endpoints y claves de una suscripción.

Cerrar sesión desactiva los avisos de ese dispositivo; vuelve a activarlos después de entrar. Si caduca una suscripción, se indica en diagnóstico y Activar avisos puede renovarla. Sin Push registrado, el panel abierto comprueba pendientes en todas las pantallas sin tocar formularios sin guardar. Si falla la entrega, no se considera enviado automáticamente.

Los diagnósticos por usuario distinguen servicios no seleccionados, consultas anteriores al cambio de preferencias, cooldown, consultas antiguas/fechas futuras y el último estado de entrega. El intervalo entre avisos y los bloqueos genéricos opcionales siguen en Ajustes → Intentos bloqueados.

Web Push no sustituye a los proveedores externos de #48 ni a aprobar/editar directamente desde notificaciones de #50; esos alcances continúan pendientes. El clic del Push lleva a la pantalla de aprobación en Parental. Las pruebas automatizadas no sustituyen la prueba en el iPhone/Android real del usuario.
