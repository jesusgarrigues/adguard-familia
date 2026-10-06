# Clientes, herencia y persistencia

Cómo lee Parental los clientes de AdGuard Home, cómo se aplican los permisos temporales y dónde se guarda el estado. [Volver al README](../README.md).

## Interfaz y ajustes del cliente

La interfaz de Parental usa fondo blanco, títulos y botones negros y la fuente Inter local. En el móvil, la navegación inferior da acceso a Clientes, Solicitudes, Actividad y Ajustes. La burbuja de Solicitudes cuenta solo las pendientes visibles para tu cuenta y sigue actualizándose sin borrar formularios. En el detalle del cliente, **Cambiar icono** ofrece 12 iconos de dispositivos y **Automático**. Administradores y responsables pueden cambiar los iconos de sus clientes; la elección se guarda en SQLite y se comparte entre navegadores. Se identifica un cliente de AdGuard por su conjunto de identificadores: renombrarlo o reordenarlos conserva el icono; cambiar ese conjunto crea una identidad distinta. Las consolas se identifican por su ID de Nintendo.

En **Ajustes**, activar **Usar servicios y horarios globales** oculta la edición personalizada. Al desactivarlo se recuperan los servicios propios del cliente; si no tiene ninguno, se presenta una selección vacía. Alternar la opción conserva el borrador. Guardar muestra progreso y errores dentro de la ventana, conserva los campos si falla y comprueba el resultado en AdGuard. Si AdGuard acepta el cambio pero no se puede comprobar la lectura, **Comprobar guardado** vuelve a consultar sin reenviar la escritura. Los permisos temporales siguen aplicándose sobre la configuración permanente.

## Clientes y herencia

Los clientes persistentes, los dispositivos detectados, sus identificadores y el catálogo de servicios se leen de AdGuard. No hay clientes de ejemplo en modo real. Los dispositivos detectados pueden darse de alta desde el panel para recibir ajustes individuales.

AdGuard tiene dos grupos independientes:

- **Protección global:** filtrado, navegación segura, control parental y búsqueda segura.
- **Servicios globales:** servicios bloqueados y sus pausas programadas.

Cada ficha muestra las restricciones configuradas y permite levantarlas temporalmente, por ejemplo YouTube durante 20 minutos para el iMac de Emma. Un permiso crea una personalización temporal únicamente en el grupo correspondiente; al vencer vuelve a la configuración permanente y a su herencia. Mientras dura, los ajustes heredados siguen los cambios globales actuales.

La vista principal usa tarjetas compactas con nombre, icono, servicios restringidos y permisos con tiempo restante. Al pulsar una tarjeta se abre su detalle: excepciones activas visibles al principio, **Favoritos** para lo habitual, **Todos los servicios** con buscador y categorías para listas largas y **Ajustes** con la configuración del cliente. Los favoritos se guardan por cuenta y cliente en ese navegador. Los 142 servicios conocidos usan logos locales con colores de marca. Un servicio nuevo usa el SVG saneado enviado por AdGuard o un icono de categoría. La lista de servicios siempre se obtiene de la instancia conectada. La misma distribución se adapta al móvil.

**Configurar cliente** incluye nombre, identificadores IP/CIDR/MAC/ClientID, etiquetas, ambas herencias, filtrado, navegación segura, control parental, búsqueda segura por motor, servicios, pausas semanales, zona horaria, DNS propios, caché y exclusión de registros y estadísticas. Usa la API de clientes de AdGuard Home; los campos que no se editan se conservan.

Puedes editar la configuración permanente mientras hay permisos activos. La app aplica las excepciones temporales sobre la nueva base. Los cambios externos observables se incorporan; AdGuard no ofrece transacciones entre lecturas y escrituras, por lo que conviene evitar cambios simultáneos al mismo cliente desde varias interfaces. No renombres un cliente con permisos activos. Para cambiar el servidor conectado, finaliza primero todos los permisos.

**Configuración global** gestiona filtrado, navegación segura, control parental, búsqueda segura por motor, servicios y pausas de bloqueo. No sustituye las pantallas de administración DNS, DHCP, certificados, listas de filtros o usuarios de AdGuard. El interruptor maestro de protección se muestra como estado, se administra en AdGuard.

Los horarios son **pausas** del bloqueo, según AdGuard, no horas de bloqueo. Las tarjetas muestran restricciones configuradas, no una afirmación de que estén bloqueando en este instante: el horario y el interruptor maestro pueden suspenderlas.

## Persistencia y disponibilidad

SQLite guarda permisos y conexión en `companion-data`. La app revisa plazos cada 10 segundos y reintenta errores; si la app está parada o AdGuard no está disponible al vencer, el permiso continúa hasta recuperar la conexión. No uses `docker compose down -v` salvo que quieras borrar el estado. Haz una copia del volumen antes de actualizar. Protege el volumen y `.env`: contienen datos de acceso.
