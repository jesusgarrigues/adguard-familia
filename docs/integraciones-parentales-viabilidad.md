# Integraciones parentales: estudio del 4 de octubre de 2026

Este documento completa el alcance de estudio de #37, #38, #39 y #40. No añade conectores ni certifica cuentas reales. El usuario pide operaciones automáticas y rechaza flujos que se limiten a abrir la app oficial para conceder tiempo.

Se han revisado los repositorios y fuentes enlazados. Una librería comunitaria que contiene métodos de escritura demuestra una vía técnica a evaluar, pero no acredita que nuestra app haya concedido tiempo ni que esa vía funcione con una cuenta concreta. La autorización inicial de una cuenta es distinta de realizar manualmente cada concesión.

| Plataforma | Vía encontrada | Operaciones relevantes | Resultado para una app Docker/PWA |
| --- | --- | --- | --- |
| Google Family Link | Cliente comunitario `tducret/familylink` | Miembros, apps, uso, bloqueo y límites por app | Prototipo posible para apps; no se ha encontrado en ese cliente una concesión nativa de minutos extra del dispositivo. Requiere resolver sesión y caducidad. |
| Tiempo de uso de Apple | FamilyControls, ManagedSettings y DeviceActivity mediante código nativo | Autorización del dispositivo, selección de apps y restricciones propias | No hay un conector remoto validado desde Docker/PWA a la configuración familiar existente. Una app nativa y sus extensiones constituyen un proyecto diferente. |
| Xbox / Microsoft Family Safety | Cliente comunitario `pantherale0/pyfamilysafety` | Cuentas/dispositivos, límites, bloqueos y aprobación experimental de solicitudes de tiempo | Vía automática candidata para Xbox, con validación pendiente de unidades, solicitud nativa y autenticación. |
| PlayStation | Cliente comunitario `parkee/psnfamily` | Familia, presencia, presupuesto, horario y ampliación/reducción solo de hoy | Vía automática candidata, con un método específico de minutos extra. Requiere validar sesión, permisos, semántica y lectura real. |

## Google Family Link — #37

Fuentes revisadas: [README](https://github.com/tducret/familylink/blob/main/README.md) y [cliente](https://github.com/tducret/familylink/blob/main/src/familylink/client.py). También se revisó el [índice oficial de APIs Discovery de Google](https://github.com/googleapis/google-api-python-client/blob/main/docs/dyn/index.md): incluye Android Management, pero no Family Link. Esa observación no demuestra la inexistencia de cualquier API privada.

El cliente lee cookies de un navegador mediante `browser_cookie3`, localiza SAPISID y construye SAPISIDHASH. Necesita la sesión completa; no ofrece un OAuth propio para nuestra PWA. Un contenedor remoto no dispone por defecto del perfil del navegador del responsable. No se han copiado ni solicitado cookies en GitHub.

`set_app_limit`, `block_app`, `always_allow_app` y `remove_app_limit` modifican restricciones de apps. Un límite habitual por app no equivale a añadir 40 minutos de pantalla solo para hoy. Para excepciones temporales propias habría que conservar el valor anterior, registrar aprobación, restaurarlo al vencer y reconciliar cambios externos, con una sesión válida y persistente. Falta demostrar una operación nativa de presupuesto extra del dispositivo.

Decisión: no introducir un conector que prometa tiempo extra del dispositivo usando únicamente estos métodos. La vía por app es investigable mediante un piloto autenticado; no se ofrece un flujo asistido como sustitución.

## Tiempo de uso de Apple — #38

Fuente revisada: [react-native-device-activity](https://github.com/Kingstinct/react-native-device-activity/blob/main/README.md), que enlaza las explicaciones y autorizaciones de Apple. El código requiere app iOS, autorización, Family Controls y extensiones nativas (Activity Monitor y Shield); su distribución requiere entitlements de Apple para los identificadores correspondientes.

Los frameworks actúan mediante código nativo y autorizaciones en el dispositivo. No constituyen una API HTTP para que este servidor modifique los límites de Tiempo de uso ya configurados en la cuenta familiar de Apple. Una PWA instalada en iPhone conserva las capacidades de una web y no obtiene esos frameworks al instalarse.

Decisión: no viable con la arquitectura Docker/PWA actual como control remoto del Tiempo de uso existente. Una app nativa con restricciones propias y consentimiento podría ser un proyecto futuro, pero no satisface por sí sola el requisito original de gestionar esos controles existentes.

## Xbox / Microsoft Family Safety — #39

Fuentes revisadas: [pyfamilysafety](https://github.com/pantherale0/pyfamilysafety), [autenticación](https://github.com/pantherale0/pyfamilysafety/blob/main/docs/getting-started/authentication.md), [overrides](https://github.com/pantherale0/pyfamilysafety/blob/main/docs/guide/device-overrides.md), [solicitudes](https://github.com/pantherale0/pyfamilysafety/blob/main/docs/guide/pending-requests.md) y [código](https://github.com/pantherale0/pyfamilysafety/blob/main/pyfamilysafety/__init__.py). Se revisó además [Xbox-WebAPI](https://github.com/OpenXbox/xbox-webapi-python), cuyos proveedores no equivalen a un conector parental.

Family Safety usa la autorización del servicio familiar y admite refresh tokens. La librería implementa bloqueos por plataforma, incluyendo Xbox, y un modo experimental para solicitudes `DeviceScreenTime`. Cancelar un bloqueo de plataforma no equivale a conceder un presupuesto extra ni a retirar todos los límites.

La aprobación encontrada necesita una solicitud nativa. La documentación habla de segundos y el código multiplica `extension_time` por **100**, aunque el comentario lo llama conversión a milisegundos. Esa inconsistencia debe resolverse con protocolo y lectura real antes de conceder minutos; no debe multiplicarse a ciegas ni certificarse que 30 segundos/minutos son correctos. Los IDs de solicitudes pueden cambiar al refrescar, por lo que se necesitan identidad y control de duplicados.

Decisión: candidato para piloto automático de consulta y aprobación de solicitudes existentes. El estudio no acredita añadir una cantidad arbitraria sin solicitud ni una concesión real en Xbox. No se incluye en esta versión un botón que simule esa concesión.

## PlayStation — #40

Fuentes revisadas: [psnfamily README](https://github.com/parkee/psnfamily/blob/main/README.md), [cliente](https://github.com/parkee/psnfamily/blob/main/src/psnfamily/client.py) y licencia MIT. Se contrastó con [psn-api](https://github.com/achievements-app/psn-api), orientada principalmente a datos de usuarios, juegos y trofeos.

`psnfamily` describe la API privada de PS Family, una autenticación inicial con NPSSO del administrador familiar, tokens renovables y scope `mobile:family`. Implementa `get_playtime`, `set_today_limit`, `add_time` y `remove_time`, además de horarios y acción al llegar al límite. Los valores de tiempo son segundos. Un override de hoy y el horario semanal son dimensiones distintas; `0` elimina el override de hoy y vuelve al horario, mientras que un límite habitual de `P0D` bloquea juego. Hay que preservar el horario y comprobar el presupuesto leído, no convertir un extra en un cambio permanente.

El proyecto utiliza credenciales de cliente y hashes de consultas recuperados de una app oficial. Es una API privada que puede cambiar; que el proyecto declare una verificación no equivale a que esta aplicación la haya realizado. Se requiere autorización de cuenta, prueba de solo lectura, aprobación de cada concesión, operación durable/idempotente, manejo de resultado incierto, rate limit y verificación posterior.

Decisión: técnicamente candidato adecuado para un piloto de tiempo extra. No se ha autenticado una cuenta PSN ni se ha añadido un conector a esta versión. El alcance de #40 era evaluar viabilidad y queda concluido con este resultado.

## Condiciones de implementación de los pilotos

Mantener roles y asignaciones por dispositivo/cuenta infantil, aprobación obligatoria para solicitantes, sesión privada en el volumen, diagnóstico sin credenciales y separación de solicitud/aprobación/envío/confirmación. Ante incertidumbre, consultar el estado sin repetir una operación aditiva. Ninguna integración debe indicar «tiempo concedido» solo por completar una solicitud local.

Los estudios están terminados. Los conectores experimentales de Google, Xbox y PlayStation necesitan su propio alcance de implementación y validación autenticada; Apple requiere además una arquitectura nativa. No se publican integraciones asistidas ni simulaciones como funcionalidad real.
