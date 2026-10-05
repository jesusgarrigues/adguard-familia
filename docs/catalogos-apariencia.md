# Iconos e imágenes de Parental

Esta actualización contiene **91 iconos de clientes y software** y **80 imágenes de usuarios**, además de la opción de iniciales. Los selectores incluyen búsqueda, categorías, vista previa/selección y una zona desplazable adaptada al móvil. Todas las imágenes se sirven desde Parental; no hacen llamadas a sitios de terceros.

El catálogo completo y la procedencia/licencia de cada icono están en `assets/appearance-catalog.json`. El backend valida sus claves y el frontend carga la misma información; una prueba comprueba que ambas versiones coinciden. Las 12 claves de dispositivos y las 12 caras anteriores siguen siendo válidas.

## Dispositivos y software

- **Apple:** iMac y clásico, MacBook Air/Pro, Mac mini/Studio/Pro, iPhone moderno/con botón, iPad/Pro, Apple Watch y Apple TV.
- **Fire TV:** Stick, Lite, 4K, 4K Max, Cube y televisor Fire TV.
- **Alexa/Echo:** Alexa, Echo esférico/cilíndrico, Plus, Dot esférico/de disco/con reloj/Max, Pop, Studio, Spot clásico/moderno, Show 5/8/10/11/15/21, Hub, Flex, Input, Auto, Amazon Tap, Look, Link/Link Amp, Buds y Frames. El inventario cubre estas familias y formas, incluidos productos antiguos; las generaciones con la misma silueta comparten su representación de familia.
- **Red:** router, punto de acceso Wi‑Fi, mesh, switch Ethernet, firewall, NAS, servidor, Raspberry Pi, cámara IP, timbre y hub; coordinador Zigbee/Z-Wave.
- **Domótica:** Home Assistant y hardware Green/Yellow, ESPHome, Zigbee2MQTT, Z-Wave JS, Mosquitto/MQTT, Node-RED, openHAB, Domoticz, Homebridge, Frigate, Scrypted, ioBroker y Matter Server.
- **Autohospedados:** Proxmox VE/Backup Server, Docker, Portainer, Grafana e InfluxDB.

Los dispositivos utilizan ilustraciones propias a color. Los logos de software provienen de Simple Icons y Dashboard Icons; los SVG de Domoticz, Scrypted y Z-Wave JS contienen una imagen PNG original embebida. Matter Server utiliza una ilustración propia identificada como tal. Proxmox VE y Backup Server comparten la marca Proxmox.

El icono Automático utiliza nombre y etiquetas como orientación, respetando las etiquetas de tipo explícitas; no identifica por hardware una generación exacta. La selección manual prevalece y se conserva mediante los identificadores del cliente aunque cambie su nombre. Un icono visual de Alexa/Home Assistant/Proxmox no amplía las capacidades de control parental: los servicios bloqueables se obtienen dinámicamente de AdGuard.

Referencias para el inventario de dispositivos: [familia Amazon Echo](https://developer.amazon.com/en-US/docs/alexa/alexa-voice-service/echo-reference.html) y [dispositivos Fire TV](https://developer.amazon.com/docs/device-specs/device-specifications-fire-tv-streaming-media-player.html). Este catálogo documenta las representaciones disponibles; no afirma incluir una silueta distinta para todas las revisiones internas/regionales del hardware ni todos los futuros modelos.

## Imágenes de usuarios

32 personas, 24 animales, 12 robots originales y 12 aficiones/objetos. La persona puede cambiar su imagen en Mi perfil; el administrador puede cambiarla al editar Usuarios y roles. Cambiar una imagen conserva los permisos y la sesión.

## Procedencia y licencias

- Ilustraciones propias: MIT, `assets/licenses/parental-artwork.txt`.
- Simple Icons: revisión `98820a4dc8c363ca72fa2c0d294ea4a0a9bba75d`, CC0, `assets/licenses/simple-icons.txt`. Se conservan geometrías y se aplican colores de su catálogo.
- Dashboard Icons: revisión `adca944175c9a3eb0471f78a4da87f237476d585`, Apache 2.0, `assets/licenses/dashboard-icons.txt`. Alexa, Domoticz, Scrypted y Z-Wave JS; su procedencia exacta está en el JSON del catálogo.
- Los nombres/logos identifican sus respectivos productos y mantienen los derechos de marca correspondientes; no se presentan como marcas de Parental.
