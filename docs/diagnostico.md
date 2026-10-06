# Diagnóstico de conexión

[Volver al README](../README.md).

En **Ajustes → Integraciones → AdGuard Home**, usa **Probar conexión** y **Actualizar diagnóstico**. El panel distingue HTTP 401/403/404, timeout, DNS, conexión rechazada, certificados y respuestas no JSON, indicando el endpoint. Los últimos 100 resultados se conservan en memoria; los fallos se registran también con `docker compose logs --tail=100 companion`. No se registran contraseñas ni cabeceras de autorización. La actualización automática se pausa en las conexiones de AdGuard y Nintendo y mientras se editan formularios.
