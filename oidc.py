"""Authentik OIDC login and explicit linking; Parental remains the authority for roles."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import jwt
import auth

CALLBACK = '/api/auth/oidc/callback'
COOKIE = '__Host-parental_oidc'
ALGORITHMS = ('RS256', 'RS384', 'RS512', 'ES256', 'ES384', 'ES512')


class OIDCError(ValueError):
    pass


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def validated_url(value, *, origin=False):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 33 for c in value):
        raise OIDCError('URL inválida: utiliza HTTPS y una dirección explícita')
    try:
        url = urllib.parse.urlsplit(value)
        port = url.port
    except ValueError:
        raise OIDCError('URL inválida') from None
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment or url.query:
        raise OIDCError('Utiliza una URL HTTPS sin credenciales, consulta ni fragmento')
    if origin and url.path not in ('', '/'):
        raise OIDCError('La URL pública debe ser el origen HTTPS de Parental, sin subruta')
    return value.rstrip('/') if origin else value


def destination(value):
    """Never return an external URL; preserve only the application's typed alert target."""
    if not isinstance(value, str) or len(value) > 2048 or any(ord(c) < 32 for c in value):
        return '/'
    try:
        url = urllib.parse.urlsplit(value)
    except ValueError:
        return '/'
    if url.scheme or url.netloc or url.path != '/' or '\\' in value:
        return '/'
    query = urllib.parse.parse_qs(url.query)
    view = query.get('view', ['clients'])[0]
    if view not in ('clients', 'requests', 'settings'):
        view = 'clients'
    fragment = urllib.parse.parse_qs(url.fragment)
    suffix = ''
    if view == 'requests' and fragment.get('request', [''])[0].isdigit():
        number = fragment['request'][0]
        if 0 < int(number) <= 999999999999999:
            suffix = '#request=' + number
    elif view == 'clients' and fragment.get('client'):
        client = fragment['client'][0]
        service = fragment.get('service', [''])[0]
        if len(client) <= 256 and len(service) <= 128 and not any(ord(c) < 32 for c in client + service):
            suffix = '#' + urllib.parse.urlencode({'client': client, **({'service': service} if service else {})})
    return '/?view=' + view + suffix


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Connector:
    def __init__(self, folder):
        self.path = Path(folder) / 'authentik.json'
        self.lock = threading.RLock()
        self.cache = None

    def config(self):
        with self.lock:
            if not self.path.exists():
                return {'enabled': False, 'revision': ''}
            try:
                return json.loads(self.path.read_text())
            except (ValueError, OSError):
                raise OIDCError('No se pudo leer la configuración Authentik') from None

    def public_config(self):
        cfg = self.config()
        return {key: cfg.get(key, '') for key in ('enabled', 'issuer', 'discovery_url', 'client_id', 'public_url')} | {
            'secret_set': bool(cfg.get('client_secret')),
            'callback_url': cfg.get('public_url', '') + CALLBACK if cfg.get('public_url') else '',
        }

    def login_enabled(self):
        try:
            return bool(self.config().get('enabled'))
        except OIDCError:
            return False

    def save(self, actor, body, ip):
        auth.require(actor, 'admin')
        auth.reauthenticate(actor, body.get('password'), ip)
        with self.lock, auth.LOCK:
            old = self.config()
            enabled = body.get('enabled', False)
            if type(enabled) is not bool:
                raise OIDCError('La opción de habilitar debe ser booleana')
            cfg = {'enabled': enabled, 'revision': secrets.token_urlsafe(24)}
            for key in ('issuer', 'discovery_url', 'client_id', 'public_url'):
                value = body.get(key, old.get(key, ''))
                if not isinstance(value, str) or len(value) > 2048:
                    raise OIDCError('Configuración Authentik inválida')
                cfg[key] = value.strip()
            secret = body.get('client_secret') or old.get('client_secret', '')
            if not isinstance(secret, str) or len(secret) > 4096:
                raise OIDCError('Secreto de cliente inválido')
            cfg['client_secret'] = secret
            if enabled or any(cfg[key] for key in ('issuer', 'discovery_url', 'public_url')):
                cfg['issuer'] = validated_url(cfg['issuer'])
                cfg['discovery_url'] = validated_url(cfg['discovery_url'])
                cfg['public_url'] = validated_url(cfg['public_url'], origin=True)
            if enabled and (not cfg['client_id'] or not secret):
                raise OIDCError('Indica client ID y secreto antes de habilitar Authentik')
            temp = self.path.with_suffix('.tmp')
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as file:
                json.dump(cfg, file)
            os.chmod(temp, 0o600)
            os.replace(temp, self.path)
            self.cache = None
            auth.DB.execute('DELETE FROM oidc_flows')
            auth.DB.execute("DELETE FROM sessions WHERE auth_provider='authentik'")
            auth.DB.commit()
            auth.audit(actor, 'authentik_configured', {'enabled': enabled})
            return self.public_config()

    def http_json(self, url, data=None):
        validated_url(url)
        headers = {'Accept': 'application/json', 'User-Agent': 'Parental-OIDC/1.0'}
        if data is not None:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        request = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data is not None else None, headers=headers)
        try:
            with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
                content = response.read(262145)
                if len(content) > 262144:
                    raise OIDCError('La respuesta Authentik supera el tamaño permitido')
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise OIDCError('Respuesta Authentik inválida')
                return parsed
        except urllib.error.HTTPError as error:
            raise OIDCError('Authentik respondió HTTP ' + str(error.code) + '; revisa la conexión y el proveedor') from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            if isinstance(error, OIDCError):
                raise
            raise OIDCError('No se pudo conectar con Authentik; revisa DNS, HTTPS y el proxy') from None

    def metadata(self, cfg, force=False):
        with self.lock:
            if not force and self.cache and self.cache[0] == cfg['revision'] and self.cache[1] > time.time():
                return self.cache[2]
        data = self.http_json(cfg['discovery_url'])
        if data.get('issuer') != cfg['issuer']:
            raise OIDCError('El issuer del descubrimiento no coincide con el configurado')
        discovery_origin = urllib.parse.urlsplit(cfg['discovery_url']).netloc
        for key in ('authorization_endpoint', 'token_endpoint', 'jwks_uri'):
            validated_url(data.get(key))
            if urllib.parse.urlsplit(data[key]).netloc != discovery_origin:
                raise OIDCError('Los endpoints OIDC deben pertenecer al servidor de descubrimiento configurado')
        if 'S256' not in data.get('code_challenge_methods_supported', []):
            raise OIDCError('Configura un proveedor Authentik que admita PKCE S256')
        if 'authorization_code' not in data.get('grant_types_supported', ['authorization_code']):
            raise OIDCError('Habilita Authorization Code en Authentik')
        with self.lock:
            self.cache = (cfg['revision'], time.time() + 300, data)
        return data

    def test(self, actor):
        auth.require(actor, 'admin')
        cfg = self.config()
        if not cfg.get('discovery_url'):
            raise OIDCError('Guarda la configuración de Authentik antes de probarla')
        metadata = self.metadata(cfg, force=True)
        keys = self.http_json(metadata['jwks_uri']).get('keys', [])
        if not any(key.get('kty') in ('RSA', 'EC') and key.get('use', 'sig') == 'sig' for key in keys if isinstance(key, dict)):
            raise OIDCError('Selecciona una clave de firma asimétrica en el proveedor Authentik')
        return {'ok': True, 'message': 'Descubrimiento, issuer, PKCE y claves de firma correctos. Falta validar un inicio de sesión real.'}

    def _actor_session(self, flow):
        row = auth.DB.execute('SELECT u.id FROM sessions s JOIN users u ON s.user_id=u.id WHERE s.token=? AND s.expires>? AND u.active=1', (flow['session_hash'], time.time())).fetchone()
        if not row or row['id'] != flow['user_id']:
            raise auth.Forbidden('La sesión local ha caducado. Inicia de nuevo la vinculación')

    def begin(self, target='/', actor=None, session_token='', password=None, ip=''):
        cfg = self.config()
        if not cfg.get('enabled') or not auth.configured():
            raise OIDCError('Authentik no está habilitado')
        if actor:
            auth.reauthenticate(actor, password, ip)
        now=time.time()
        with auth.LOCK:
            key=digest('oidc-start|'+ip)
            old=auth.DB.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
            count=old['count']+1 if old and old['until']>now else 1
            if count>30: raise OIDCError('Demasiados inicios de sesión. Espera cinco minutos')
            auth.DB.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(key,count,now+300 if not old or old['until']<=now else old['until']));auth.DB.commit()
        metadata = self.metadata(cfg)
        state, binding, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
        now = time.time()
        with auth.LOCK:
            auth.DB.execute('DELETE FROM oidc_flows WHERE expires<?', (now,))
            if auth.DB.execute('SELECT count(*) FROM oidc_flows').fetchone()[0] >= 1024:
                raise OIDCError('Demasiados accesos pendientes; espera unos minutos')
            # A browser has one outstanding login/link flow. Replace only its own binding upstream.
            auth.DB.execute('INSERT INTO oidc_flows(state,binding,kind,user_id,session_hash,nonce,verifier,revision,expires,target) VALUES(?,?,?,?,?,?,?,?,?,?)', (digest(state), digest(binding), 'link' if actor else 'login', actor['id'] if actor else None, digest(session_token) if actor else None, nonce, verifier, cfg['revision'], now + 600, destination(target)))
            auth.DB.commit()
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        params = {'client_id': cfg['client_id'], 'redirect_uri': cfg['public_url'] + CALLBACK, 'response_type': 'code', 'scope': 'openid profile', 'state': state, 'nonce': nonce, 'code_challenge': challenge, 'code_challenge_method': 'S256'}
        if actor:
            params['prompt'] = 'login'
        return metadata['authorization_endpoint'] + '?' + urllib.parse.urlencode(params), binding

    def verify_token(self, token, cfg, metadata, nonce):
        try:
            if not isinstance(token, str) or len(token) > 32768:
                raise OIDCError('Authentik no devolvió un ID token válido')
            header = jwt.get_unverified_header(token)
            if header.get('alg') not in ALGORITHMS or not isinstance(header.get('kid'), str):
                raise OIDCError('Selecciona una clave de firma asimétrica en Authentik')
            keys = self.http_json(metadata['jwks_uri']).get('keys', [])
            matches = [key for key in keys if isinstance(key, dict) and key.get('kid') == header['kid'] and key.get('use', 'sig') == 'sig' and key.get('alg', header['alg']) == header['alg']]
            if len(matches) != 1:
                raise OIDCError('No se encontró una clave de firma inequívoca para el ID token')
            key = jwt.PyJWK.from_dict(matches[0], algorithm=header['alg'])
            claims = jwt.decode(token, key.key, algorithms=[header['alg']], audience=cfg['client_id'], issuer=cfg['issuer'], leeway=10, options={'require': ['exp', 'iat', 'iss', 'aud', 'sub', 'nonce']})
            if not isinstance(claims.get('nonce'), str) or not hmac.compare_digest(claims['nonce'], nonce):
                raise OIDCError('El nonce de Authentik no coincide')
            aud = claims['aud']
            if isinstance(aud, list) and len(aud) > 1 and claims.get('azp') != cfg['client_id']:
                raise OIDCError('El ID token no autoriza a este cliente')
            if 'azp' in claims and claims['azp'] != cfg['client_id']:
                raise OIDCError('El ID token pertenece a otro cliente')
            subject = claims['sub']
            if not isinstance(subject, str) or not subject or len(subject) > 512 or any(ord(c) < 32 for c in subject):
                raise OIDCError('Identidad Authentik inválida')
            label = claims.get('preferred_username') or claims.get('name') or 'Usuario Authentik'
            if not isinstance(label, str):
                label = 'Usuario Authentik'
            return {'issuer': cfg['issuer'], 'subject': subject, 'label': label[:160]}
        except jwt.PyJWTError:
            raise OIDCError('El ID token no supera la validación de firma, identidad o caducidad') from None
        except (TypeError, KeyError):
            raise OIDCError('Respuesta de identidad Authentik inválida') from None

    def callback(self, state, code, binding):
        if not all(isinstance(x, str) and 0 < len(x) <= 4096 for x in (state, code, binding)):
            raise OIDCError('La respuesta de Authentik está incompleta; inicia de nuevo')
        cfg = self.config()
        with auth.LOCK:
            flow = auth.DB.execute('SELECT * FROM oidc_flows WHERE state=?', (digest(state),)).fetchone()
            if not flow or flow['kind'] not in ('login', 'link') or flow['expires'] < time.time() or flow['revision'] != cfg['revision'] or not cfg.get('enabled') or not hmac.compare_digest(flow['binding'], digest(binding)):
                raise OIDCError('El acceso ha caducado, ya se utilizó o pertenece a otro navegador')
            # Consume before any network operation. Never retry a code whose exchange may have succeeded.
            auth.DB.execute('DELETE FROM oidc_flows WHERE state=?', (digest(state),)); auth.DB.commit()
            if flow['kind'] == 'link':
                self._actor_session(flow)
        metadata = self.metadata(cfg)
        tokens = self.http_json(metadata['token_endpoint'], {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': cfg['public_url'] + CALLBACK, 'client_id': cfg['client_id'], 'client_secret': cfg['client_secret'], 'code_verifier': flow['verifier']})
        identity = self.verify_token(tokens.get('id_token'), cfg, metadata, flow['nonce'])
        with self.lock, auth.LOCK:
            if self.config().get('revision') != cfg['revision']:
                raise OIDCError('La configuración Authentik cambió; inicia de nuevo')
            if flow['kind'] == 'link':
                self._actor_session(flow)
                confirmation = secrets.token_urlsafe(32)
                auth.DB.execute('INSERT INTO oidc_flows(state,binding,kind,user_id,session_hash,nonce,verifier,revision,expires,target,identity) VALUES(?,?,?,?,?,?,?,?,?,?,?)', (digest(confirmation), flow['binding'], 'confirm', flow['user_id'], flow['session_hash'], confirmation, '', cfg['revision'], time.time() + 300, '/?view=settings', json.dumps(identity)))
                auth.DB.commit()
                return {'target': '/?view=settings#authentik=confirm', 'link': True}
            row = auth.DB.execute('SELECT u.* FROM users u JOIN external_identities e ON e.user_id=u.id WHERE e.issuer=? AND e.subject=? AND u.active=1', (identity['issuer'], identity['subject'])).fetchone()
            if not row:
                raise OIDCError('Esta identidad no está vinculada a una cuenta activa. Entra con tu contraseña local y vincúlala desde Mi perfil')
            token, csrf, user = auth.issue_session(row, 'authentik', identity['issuer'], identity['subject'])
            return {'target': flow['target'], 'token': token, 'csrf': csrf, 'user': user, 'link': False}

    def status(self, actor, session_token='', binding=''):
        cfg = self.config()
        with auth.LOCK:
            row = auth.DB.execute('SELECT issuer,label,linked FROM external_identities WHERE user_id=?', (actor['id'],)).fetchone()
            result = {'enabled': bool(cfg.get('enabled')), 'linked': bool(row), 'identity': dict(row) if row else None, 'pending': None}
            if binding and session_token:
                pending = auth.DB.execute("SELECT * FROM oidc_flows WHERE kind='confirm' AND user_id=? AND session_hash=? AND binding=? AND expires>? AND revision=? ORDER BY expires DESC LIMIT 1", (actor['id'], digest(session_token), digest(binding), time.time(), cfg['revision'])).fetchone()
                if pending:
                    result['pending'] = {'confirmation': pending['nonce'], 'label': json.loads(pending['identity'])['label'], 'expires': pending['expires']}
            return result

    def confirm(self, actor, confirmation, session_token, binding, cancel=False):
        if not isinstance(confirmation, str) or len(confirmation) > 128:
            raise OIDCError('Confirmación inválida')
        cfg = self.config()
        with self.lock, auth.LOCK:
            row = auth.DB.execute("SELECT * FROM oidc_flows WHERE state=? AND kind='confirm'", (digest(confirmation),)).fetchone()
            if not row or row['user_id'] != actor['id'] or row['session_hash'] != digest(session_token) or row['binding'] != digest(binding) or row['expires'] < time.time() or row['revision'] != cfg['revision'] or not cfg.get('enabled'):
                raise OIDCError('La confirmación ha caducado o no pertenece a esta sesión')
            self._actor_session(row)
            auth.DB.execute('DELETE FROM oidc_flows WHERE state=?', (row['state'],)); auth.DB.commit()
            if cancel:
                return {'ok': True}
            identity = json.loads(row['identity'])
            if auth.DB.execute('SELECT 1 FROM external_identities WHERE user_id=?', (actor['id'],)).fetchone():
                raise OIDCError('La cuenta ya está vinculada. Desvincula antes de cambiar la identidad')
            try:
                auth.DB.execute('INSERT INTO external_identities VALUES(?,?,?,?,?)', (actor['id'], identity['issuer'], identity['subject'], identity['label'], time.time())); auth.DB.commit()
            except __import__('sqlite3').IntegrityError:
                auth.DB.rollback()
                raise OIDCError('Esta identidad Authentik ya pertenece a otra cuenta de Parental') from None
            auth.audit(actor, 'authentik_linked', {'user_id': actor['id']})
            return {'ok': True}

    def unlink(self, actor, body, ip):
        uid = body.get('user_id', actor['id'])
        if type(uid) is not int:
            raise OIDCError('Usuario inválido')
        if uid != actor['id']:
            auth.require(actor, 'admin')
        auth.reauthenticate(actor, body.get('password'), ip)
        with auth.LOCK:
            user = auth.DB.execute('SELECT password FROM users WHERE id=?', (uid,)).fetchone()
            if not user or not user['password']:
                raise OIDCError('La cuenta necesita una contraseña local operativa antes de desvincularse')
            auth.DB.execute('DELETE FROM external_identities WHERE user_id=?', (uid,))
            auth.DB.execute("DELETE FROM sessions WHERE user_id=? AND auth_provider='authentik'", (uid,))
            auth.DB.execute('DELETE FROM oidc_flows WHERE user_id=?', (uid,)); auth.DB.commit()
            auth.audit(actor, 'authentik_unlinked', {'user_id': uid})
            return {'ok': True}
