# Nintendo: diagnóstico y validación real pendientes (#34 y #35)

Actualización del 4 de octubre de 2026 tras la autorización «implemente todos los cambios pendientes».

El código ya separa presupuesto extra diario y hora tope, confirma solo presupuesto con `withBedtime=False`, compone 40 minutos, conserva resultados inciertos y permite cerrar su seguimiento sin reenviar tiempo. Se ha revisado de nuevo la lectura `extraPlayingTime.inOneDay.duration`, el horario efectivo y la secuencia de confirmación. No se ha encontrado en esta revisión evidencia que permita atribuir el caso real a una nueva causa concreta ni justificar un cambio especulativo en la API.

No hay acceso autenticado a la cuenta o consola del usuario en este entorno. Se ha pedido el diagnóstico saneado de la operación mediante «Detalles del seguimiento». Hasta disponer de esa evidencia, #34 y #35 permanecen abiertas; los tests con FakeBackend no certifican la consola real.

## Evidencia necesaria

Usar el botón existente **Copiar diagnóstico** dentro de **Detalles del seguimiento**. Incluye pedido, presupuesto anterior/objetivo/leído, hora esperada/leída, respuesta de Nintendo, etapa, confirmación y fechas. No copiar sesión, código de login, token ni contenido del volumen. No publicar nombres privados de consola/cuenta sin anonimizar.

La comparación debe utilizar una misma operación y una lectura nueva. Si se ha modificado desde la app oficial, registrar el momento del cambio: un presupuesto mayor después no demuestra que la concesión original funcionara.

## Matriz prevista

1. Base diaria 0: concesiones aprobadas de 15, 40 y 60 minutos; anotar uso y presupuesto previo, objetivo y lectura posterior.
2. Con presupuesto consumido o pendiente: distinguir añadir al total extra de hoy de garantizar minutos jugables desde ahora.
3. Mantener descanso: confirmar minutos sin modificar la hora; probar una cantidad mayor que la ventana restante sin exigir automáticamente ampliar horario.
4. Ampliar descanso autorizado: comprobar por separado presupuesto y hora efectiva.
5. Cancelar ampliación de hoy creada desde nuestra app y desde la app oficial; comparar la lectura sin enviar cancelaciones extra.
6. Consola offline y sincronización retrasada: separar aceptación de nube, lectura y sincronización de consola.
7. Respuesta incierta/cambio externo: comprobar estado sin reenviar la concesión; cerrar seguimiento solo tras revisar presupuesto actual.

Las operaciones aditivas se aprueban una vez, se registran y no se repiten para «probar». La matriz se ejecutará con la cuenta/consola real y observaciones de juego. Publicar un informe técnico no cierra estas validaciones.
