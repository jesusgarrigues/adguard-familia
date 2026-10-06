# Actualizar desde adguard-familia

[Volver al README](../README.md).

En el Compose de tu instalación actual cambia **las dos referencias de imagen**, incluidas preparar-datos y companion, a `jesusgarrigues/parental:latest` (o `${DOCKERHUB_USERNAME}/parental:${IMAGE_TAG:-latest}`). Conserva `.env`, el nombre del servicio, el volumen y el mismo directorio/nombre de proyecto Compose. Si cambias de directorio, utiliza `docker compose -p <nombre-del-proyecto-existente>` para seguir utilizando el volumen existente. Comprueba tu proyecto con `docker compose ls` y haz copia del volumen antes de actualizar.

```sh
docker compose pull
docker compose up -d
```

No uses `down -v` ni crees un volumen nuevo para este cambio de nombre. Los datos, usuarios, solicitudes y conexiones permanecen en el volumen existente. El repositorio anterior de GitHub redirige a parental; Docker Hub conserva la imagen antigua, pero las nuevas publicaciones utilizan parental.
