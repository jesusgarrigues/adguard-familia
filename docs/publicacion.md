# Publicar en GitHub y Docker Hub

[Volver al README](../README.md).

El workflow `.github/workflows/docker.yml` ejecuta pruebas y publica imágenes multi arquitectura desde `main` y etiquetas `v*`. En GitHub → Settings → Secrets and variables → Actions configura:

- Variable **DOCKERHUB_USERNAME**: usuario u organización de Docker Hub.
- Secreto **DOCKERHUB_TOKEN**: token de Docker Hub con permisos de escritura al repositorio `parental`.

No subas el token a archivos ni commits. Crea el repositorio Docker Hub `parental` en tu cuenta y elige su visibilidad. Para publicar una versión estable, crea una etiqueta como `v0.2.0` después de superar las pruebas. Hasta que el workflow termine correctamente, la imagen no está disponible para instalar.
