# AdGuard Familia

Panel autohospedable para AdGuard Home, orientado a cada cliente. Lee los clientes y sus ajustes dinámicamente, gestiona la configuración global y las personalizaciones y levanta restricciones durante un plazo concreto.

## Instalar desde Docker Hub

Una vez publicada la imagen `<usuario-dockerhub>/adguard-familia`:

1. Descarga `compose.yaml` y `.env.example` de este repositorio.
2. Copia `.env.example` a `.env`, introduce `DOCKERHUB_USERNAME` y sustituye `APP_TOKEN` por una clave aleatoria.
3. Ejecuta:

```sh
docker compose pull
docker compose up -d
```

Abre http://localhost:8080, introduce APP_TOKEN y configura la URL, usuario y contraseña de AdGuard en **Servidor**. Puedes probar la conexión antes de guardarla. La configuración se conserva en el volumen; la contraseña no se devuelve al navegador. Puedes usar variables ADGUARD_* en .env como configuración inicial.

Para acceder desde tu LAN, configura `BIND_ADDRESS=0.0.0.0` y abre la IP del servidor. Usa un proxy inverso con HTTPS para acceso remoto y notificaciones de navegador desde la LAN. La URL de AdGuard incluye su puerto web, no su puerto DNS. `localhost` dentro del contenedor apunta a la app; para otro contenedor usa una red Docker compartida y el nombre de servicio.

Las imágenes publicadas por el workflow admiten `linux/amd64` y `linux/arm64`. `latest` y `edge` se actualizan tras superar las pruebas en `main`; las etiquetas `v*` añaden versiones numeradas. Puedes fijar `IMAGE_TAG` a una versión publicada.

## Clientes y herencia

Los clientes persistentes, los dispositivos detectados, sus identificadores y el catálogo de servicios se leen de AdGuard. No hay clientes de ejemplo en modo real. Los dispositivos detectados pueden darse de alta desde el panel para recibir ajustes individuales.

AdGuard tiene dos grupos independientes:

- **Protección global:** filtrado, navegación segura, control parental y búsqueda segura.
- **Servicios globales:** servicios bloqueados y sus pausas programadas.

Cada ficha muestra las restricciones configuradas y permite levantarlas temporalmente, por ejemplo YouTube durante 20 minutos para el iMac de Emma. Un permiso crea una personalización temporal únicamente en el grupo correspondiente; al vencer vuelve a la configuración permanente y a su herencia. Mientras dura, los ajustes heredados siguen los cambios globales actuales.

**Configurar cliente** incluye nombre, identificadores IP/CIDR/MAC/ClientID, etiquetas, ambas herencias, filtrado, navegación segura, control parental, búsqueda segura por motor, servicios, pausas semanales, zona horaria, DNS propios, caché y exclusión de registros y estadísticas. Usa la API de clientes de AdGuard Home; los campos que no se editan se conservan.

Puedes editar la configuración permanente mientras hay permisos activos. La app aplica las excepciones temporales sobre la nueva base. Los cambios externos observables se incorporan; AdGuard no ofrece transacciones entre lecturas y escrituras, por lo que conviene evitar cambios simultáneos al mismo cliente desde varias interfaces. No renombres un cliente con permisos activos. Para cambiar el servidor conectado, finaliza primero todos los permisos.

**Configuración global** gestiona filtrado, navegación segura, control parental, búsqueda segura por motor, servicios y pausas de bloqueo. No sustituye las pantallas de administración DNS, DHCP, certificados, listas de filtros o usuarios de AdGuard. El interruptor maestro de protección se muestra como estado, se administra en AdGuard.

Los horarios son **pausas** del bloqueo, según AdGuard, no horas de bloqueo. Las tarjetas muestran restricciones configuradas, no una afirmación de que estén bloqueando en este instante: el horario y el interruptor maestro pueden suspenderlas.

## Avisos

El registro de consultas alimenta la actividad bloqueada y ofrece permisos temporales desde el evento. Los avisos del navegador requieren HTTPS o localhost, permiso y mantener el panel abierto. No hay push con el navegador cerrado ni integración de correo/Telegram.

Una consulta puede proceder de actividad en segundo plano. Se agrupan avisos por cliente y restricción cada 5 minutos, se leen las últimas 500 consultas cada 10 segundos y se guardan los últimos 500 eventos. Con mucho tráfico o desconexiones pueden perderse eventos. Un cliente excluido del registro no genera avisos. Para avisos de filtrado DNS se desactiva temporalmente el filtrado del cliente completo; no se crea una excepción solo para el dominio del aviso.

DNS no garantiza detener un vídeo o conexión ya abiertos al caducar: las cachés y conexiones persistentes pueden retrasarlo. DNS externo, VPN o DNS cifrado pueden evitar el filtro. El registro DNS no revela búsquedas individuales en páginas HTTPS.

## Persistencia y disponibilidad

SQLite guarda permisos y conexión en `companion-data`. La app revisa plazos cada 10 segundos y reintenta errores; si la app está parada o AdGuard no está disponible al vencer, el permiso continúa hasta recuperar la conexión. No uses `docker compose down -v` salvo que quieras borrar el estado. Haz una copia del volumen antes de actualizar. Protege el volumen y `.env`: contienen datos de acceso.

## Desarrollo y demostración

```sh
cp .env.example .env
# Define APP_TOKEN. Opcional: DEMO=true para probar sin AdGuard.
docker compose -f compose.build.yaml up -d --build
```

El modo demostración simula Emma y Martín; no cambia ningún AdGuard real. El diseño sigue la maqueta oscura con clientes, permisos con cuenta atrás, actividad y ajustes.

```sh
python -m unittest -v test_app.py
```

Pruebas de caducidad tras reinicio, permisos simultáneos, herencia global, cambios globales y de cliente durante permisos, recuperación de errores, clientes dinámicos, validación y protección de credenciales. La integración debe verificarse con la versión instalada de AdGuard Home; las pruebas locales usan el simulador.

## Publicar en GitHub y Docker Hub

El workflow `.github/workflows/docker.yml` ejecuta pruebas y publica imágenes multi arquitectura desde `main` y etiquetas `v*`. En GitHub → Settings → Secrets and variables → Actions configura:

- Variable **DOCKERHUB_USERNAME**: usuario u organización de Docker Hub.
- Secreto **DOCKERHUB_TOKEN**: token de Docker Hub con permisos de escritura al repositorio `adguard-familia`.

No subas el token a archivos ni commits. Crea el repositorio Docker Hub `adguard-familia` en tu cuenta y elige su visibilidad. Para publicar una versión estable, crea una etiqueta como `v0.2.0` después de superar las pruebas. Hasta que el workflow termine correctamente, la imagen no está disponible para instalar.

## Diagnóstico de conexión

En **Servidor**, usa **Probar conexión** y **Actualizar diagnóstico**. El panel distingue HTTP 401/403/404, timeout, DNS, conexión rechazada, certificados y respuestas no JSON, indicando el endpoint. Los últimos 100 resultados se conservan en memoria; los fallos se registran también con `docker compose logs --tail=100 adguard-familia`. No se registran contraseñas ni cabeceras de autorización. La actualización automática se pausa en Servidor y mientras se editan formularios.
