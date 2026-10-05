# Iniciar sesión con Authentik

Parental puede utilizar tu Authentik autohospedado como proveedor OpenID Connect. Los usuarios, roles, dispositivos asignados y solicitudes siguen guardados en Parental. Primero crea o conserva las cuentas locales; cada persona vincula su propia identidad de Authentik.

## Configurar Authentik

1. En la administración de Authentik, abre **Applications → Applications → New Application** y crea una aplicación llamada Parental, con slug `parental`.
2. Elige un proveedor **OAuth2/OIDC**, cliente **Confidential**, y habilita **Authorization Code** y **PKCE S256**. Selecciona los scope mappings `openid` y `profile`.
3. Selecciona una **Signing Key** asimétrica, por ejemplo RSA/RS256. No actives cifrado de ID tokens en esta versión.
4. En Redirect URIs registra, con comparación estricta, la dirección exacta que muestra Parental. Por ejemplo: `https://parental.example.com/api/auth/oidc/callback`. No utilices comodines.
5. Copia el Client ID y Client secret en la configuración privada de Parental. Nunca los publiques en incidencias o mensajes.

Con el issuer por aplicación habitual de Authentik:

| Campo | Ejemplo |
| --- | --- |
| Issuer esperado | `https://auth.example.com/application/o/parental/` |
| Descubrimiento OIDC | `https://auth.example.com/application/o/parental/.well-known/openid-configuration` |
| URL pública de Parental | `https://parental.example.com` |

Comprueba los valores reales del documento de descubrimiento. Si Authentik utiliza issuer global, el issuer puede ser `https://auth.example.com/`, mientras el documento de descubrimiento sigue estando bajo `/application/o/parental/`. Ambos campos se configuran por separado.

El navegador debe llegar a las dos aplicaciones y el contenedor de Parental debe llegar por HTTPS a los endpoints de descubrimiento, token y JWKS de Authentik. Los endpoints deben pertenecer al servidor de descubrimiento configurado. Utiliza certificados válidos y evita desafíos interactivos del proxy en esos endpoints. Esta versión sirve Parental desde la raíz de su dominio, sin prefijo de subruta.

## Configurar Parental

Entra como administrador con tu contraseña local y abre **Ajustes → Parental → Acceso e identidad · Authentik**. Introduce los valores anteriores, habilita el acceso y confirma tu contraseña local al guardar. El secreto vacío conserva el ya guardado; la interfaz solo muestra si existe.

Pulsa **Probar configuración guardada**. Esta prueba comprueba descubrimiento, issuer, PKCE y claves de firma; el Client ID y secreto se validan al completar un acceso real. Un resultado correcto de descubrimiento no afirma que ya se haya probado la autenticación con tu instalación.

## Vincular usuarios existentes

Cada persona realiza estos pasos con su cuenta local:

1. **Ajustes → Mi perfil → Acceso con Authentik → Vincular Authentik**.
2. Confirmar la contraseña local de Parental.
3. Identificarse en Authentik.
4. De vuelta en Parental, revisar las dos cuentas y pulsar **Vincular estas cuentas**. La confirmación caduca a los cinco minutos.

Después aparece **Continuar con Authentik** al entrar. La cuenta conserva su ID, rol, avatar, clientes, límites e historial. No se crean cuentas automáticamente ni se unen por coincidencia de nombre o correo. Los grupos enviados por Authentik no conceden permisos en Parental. Una identidad externa no puede pertenecer a dos cuentas; una cuenta desactivada no puede entrar por ninguna vía.

El administrador ve el estado de vinculación al editar una cuenta en **Usuarios y roles** y puede desvincularla confirmando su propia contraseña local. La vinculación inicial exige que la persona pruebe las dos identidades desde su perfil; no hay importación masiva ni asignación arbitraria por nombre.

## Recuperación y sesiones

El inicio de sesión local sigue disponible. Mantén una contraseña local de administrador operativa. Cambiar la configuración Authentik cancela operaciones de acceso pendientes y cierra las sesiones SSO anteriores; las sesiones locales permanecen. Desvincular una identidad cierra sus sesiones SSO.

**Cerrar sesión** cierra la sesión de Parental. El cierre global de Authentik y sus mecanismos front/back-channel no están implementados en esta versión. Si Authentik conserva su sesión, puede identificarte de nuevo al pulsar su botón; las vinculaciones solicitan una autenticación nueva.

Las sesiones normales utilizan cookies HttpOnly y SameSite=Strict. La vuelta desde Authentik utiliza una cookie transitoria independiente, `__Host-parental_oidc`, Secure/HttpOnly/SameSite=Lax, ligada al navegador, con estado y PKCE de un solo uso. No desactives HTTPS. Los destinos de avisos de solicitud o cliente se conservan tras el acceso y siguen exigiendo los permisos de la cuenta.

La configuración privada se guarda en `/data/authentik.json` con modo `0600`; identidades y transacciones se guardan en `accounts.db`. Incluye estos archivos en las copias de seguridad del volumen, sin publicarlos. No se guardan access/refresh/ID tokens después de verificar el acceso.

Fuentes: [proveedor OIDC de Authentik](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/) y [creación de proveedor](https://docs.goauthentik.io/add-secure-apps/providers/oauth2/create-oauth2-provider/). Las pruebas automatizadas utilizan un proveedor simulado con ID tokens RSA firmados. La conexión final debe configurarse y validarse con tu Authentik real.


## Google y reautenticación al vincular cuentas

Parental pide `prompt=login` al vincular una identidad a una cuenta local; el inicio de sesión ordinario no añade ese parámetro. Si Google devuelve «Flow does not apply to current user» cuando ya existe una sesión Authentik, revisa Flujos y etapas → Flujos → `default-source-authentication` → Editar → Autenticación. El requisito `Require no authentication` puede impedir reautenticación con sesión abierta. Cambiarlo a `No requirement`, conservando la política `default-source-authentication-if-sso` y la etapa de inicio de sesión, resolvió el caso confirmado por el usuario en [#73](https://github.com/jesusgarrigues/parental/issues/73). El comportamiento está reportado [en Authentik #26677](https://github.com/goauthentik/authentik/issues/26677). No eliminar las políticas SSO ni los grupos de acceso de la aplicación.
