# Instalar en Android e iPhone

[Volver al README](../README.md).

Es una app web instalable (PWA), no un paquete APK ni una app de App Store. Publica la instalación doméstica detrás de HTTPS con un certificado confiable.

- **Android:** abre el panel HTTPS en Chrome, menú → Instalar aplicación o Añadir a pantalla de inicio.
- **iPhone:** abre el panel HTTPS en Safari, Compartir → Añadir a pantalla de inicio.

En **Ajustes → Instalar Parental** encontrarás el botón de instalación cuando el navegador lo permita o las instrucciones correspondientes. Safari en iPhone no muestra el mismo aviso automático de instalación que Chrome: se ofrece una guía de **Compartir → Añadir a pantalla de inicio**. La recomendación se puede ocultar y no se muestra si la app ya está instalada.

El diseño se adapta al móvil e incluye el nuevo icono de Parental, icono de inicio de iOS de 180 px, variantes de 192/512 px, favicon, manifest y modo independiente. Se conserva el identificador de la PWA. La caché versionada guarda únicamente recursos estáticos públicos (fuentes, estilos, scripts e iconos). No se almacena contenido privado en caché y se muestra una página de desconexión si el servidor no responde. La gestión y las aprobaciones necesitan conexión. Los avisos de nuevas solicitudes y bloqueos usan Web Push cuando se registra el dispositivo; en iPhone se requiere la PWA instalada y permisos. Hay diagnóstico y pruebas diferenciadas de entrega local/desde el servidor.

Para actualizar la imagen sin borrar cuentas ni configuración:

```sh
docker compose pull
docker compose up -d
```

Después recarga el navegador. Si iOS conserva el nombre o icono anterior del acceso directo, retira solo ese acceso de la pantalla de inicio y vuelve a añadirlo desde Safari. Esto no borra las cuentas del servidor. No borres los volúmenes. Los archivos de cuentas, sesiones y auditoría se guardan en `/data/accounts.db`.
