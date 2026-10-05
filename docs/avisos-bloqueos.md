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

## Entrega

Esta versión entrega avisos de navegador mientras el panel está abierto. No incorpora Push ni proveedores externos con Parental cerrado: esos destinos se siguen en #48. La prueba del navegador y Chromium móvil no sustituye la comprobación real en Safari/iPhone o Android.
