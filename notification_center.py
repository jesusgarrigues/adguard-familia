"""Durable, scoped notifications. Receiving or reading never grants access."""
import base64, hashlib, json, os, re, time
from pathlib import Path
from urllib.parse import urlsplit
import auth, blocked_alerts


def device_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{16,80}', value):
        raise ValueError('Dispositivo de avisos inválido')
    return value


def subscription(value):
    if value is None: return None
    if not isinstance(value, dict): raise ValueError('Suscripción Push inválida')
    endpoint = value.get('endpoint')
    if not isinstance(endpoint, str) or len(endpoint) > 3072: raise ValueError('Destino Push inválido')
    url = urlsplit(endpoint)
    if (url.scheme != 'https' or url.hostname not in ('web.push.apple.com', 'fcm.googleapis.com', 'updates.push.services.mozilla.com')
            or url.username or url.password or url.port not in (None, 443) or url.fragment):
        raise ValueError('Proveedor Push no admitido; usa Safari, Chrome o Firefox')
    keys = value.get('keys')
    if not isinstance(keys, dict): raise ValueError('Claves Push inválidas')
    try:
        for name, size in (('auth', 16), ('p256dh', 65)):
            raw = keys[name]
            if not isinstance(raw, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,100}={0,2}', raw): raise ValueError()
            decoded = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4))
            if len(decoded) != size: raise ValueError()
        from cryptography.hazmat.primitives.asymmetric import ec
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), decoded)
    except (ValueError, KeyError): raise ValueError('Claves Push inválidas') from None
    return {'endpoint': endpoint, 'keys': {k: keys[k] for k in ('auth', 'p256dh')}}


class Center:
    def __init__(self, folder, clock=time.time, sender=None):
        self.clock, self.sender = clock, sender or self.send
        self.keyfile = Path(folder) / 'web-push.pem'
        with auth.LOCK:
            auth.DB.executescript('''
            CREATE TABLE IF NOT EXISTS alert_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER NOT NULL,source TEXT NOT NULL,kind TEXT NOT NULL,client TEXT NOT NULL,service TEXT NOT NULL,created REAL NOT NULL,detail TEXT NOT NULL,read_at REAL,UNIQUE(user_id,source));
            CREATE TABLE IF NOT EXISTS alert_devices(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL,subscription TEXT,created REAL NOT NULL,updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS alert_deliveries(alert_id INTEGER NOT NULL,device TEXT NOT NULL,status TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,due REAL NOT NULL,error TEXT NOT NULL DEFAULT '',PRIMARY KEY(alert_id,device));
            ''')
            auth.DB.execute('INSERT OR IGNORE INTO alert_meta VALUES(?,?)', ('started', str(clock())))
            self.started = float(auth.DB.execute("SELECT value FROM alert_meta WHERE key='started'").fetchone()[0])
            auth.DB.commit()
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        if not self.keyfile.exists():
            key = ec.generate_private_key(ec.SECP256R1())
            data = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
            try:
                fd = os.open(self.keyfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as stream: stream.write(data)
            except FileExistsError: pass
        key = serialization.load_pem_private_key(self.keyfile.read_bytes(), password=None)
        self.public_key = base64.urlsafe_b64encode(key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)).rstrip(b'=').decode()

    def user(self, uid):
        row = auth.DB.execute('SELECT * FROM users WHERE id=? AND active=1', (uid,)).fetchone()
        return auth.public(row) if row else None

    def visible(self, user, item):
        return bool(user and user['role'] in ('admin', 'responsable') and (item['kind']=='test' or user['role'] == 'admin' or item['client'] in user['clients']))

    def current(self, user, item):
        if not self.visible(user, item): return False
        if item['kind']=='test': return True
        if item['kind'] == 'request':
            rid = json.loads(item['detail'])['request_id']
            row = auth.DB.execute("SELECT status,created,client FROM requests WHERE id=?", (rid,)).fetchone()
            return bool(row and row['status'] == 'pending' and row['created'] > self.clock()-86400 and row['client'] == item['client'])
        pref = blocked_alerts.preferences(user)
        chosen = pref['preferences']['clients'].get(item['client'], pref['preferences'])
        service = item['service']
        selected = service in chosen['protections'] if service.startswith('@') else chosen['mode'] == 'all' or (chosen['mode'] == 'selected' and service in chosen['services'])
        return selected and item['created'] > pref['updated']

    def sync(self, events):
        now, reasons, made = self.clock(), {}, 0
        with auth.LOCK:
            users = [auth.public(r) for r in auth.DB.execute("SELECT * FROM users WHERE active=1 AND role IN ('admin','responsable')")]
            for user in users:
                config = blocked_alerts.preferences(user)
                evaluated,excluded=blocked_alerts.evaluate(user,events,config,now=now)
                eligible = {e['id'] for e in evaluated}
                auth.DB.execute('INSERT OR REPLACE INTO alert_meta VALUES(?,?)', ('scan:'+str(user['id']),json.dumps({'time':now,'events_in_scope':sum(self.visible(user,e) for e in events),'eligible':len(eligible),'excluded':{k:v for k,v in excluded.items() if k!='not_blocked_or_outside_scope'}})))
                for event in events:
                    if event['kind'] != 'blocked' or not self.visible(user, event): continue
                    if event['time'] < self.started or event['id'] not in eligible:
                        reasons['history_preferences_or_cooldown'] = reasons.get('history_preferences_or_cooldown', 0) + 1
                        continue
                    source = 'block:' + hashlib.sha256(json.dumps([event[k] for k in ('time','client','service','domain')], ensure_ascii=False).encode()).hexdigest()
                    made += self.insert(user, source, 'blocked', event['client'], event['service'], event['time'], {'domain': event['domain']})
                for request in auth.requests_for(user):
                    if request['status'] == 'pending' and request['created'] >= self.started:
                        made += self.insert(user, 'request:'+str(request['id']), 'request', request['client'], request['service'], request['created'], {'request_id':request['id'],'username':request['username'],'minutes':request['minutes']})
            auth.DB.execute('INSERT OR REPLACE INTO alert_meta VALUES(?,?)', ('scan', json.dumps({'time':now,'events':len(events),'created':made,'excluded':reasons})))
            # Bound retained history, without truncating the unread inbox count at a display limit.
            old = now-30*86400
            auth.DB.execute('DELETE FROM alert_deliveries WHERE alert_id IN (SELECT id FROM alerts WHERE created<?)', (old,))
            auth.DB.execute('DELETE FROM alerts WHERE created<?', (old,))
            auth.DB.commit()

    def insert(self, user, source, kind, client, service, created, detail):
        result = auth.DB.execute('INSERT OR IGNORE INTO alerts(user_id,source,kind,client,service,created,detail) VALUES(?,?,?,?,?,?,?)', (user['id'],source,kind,client,service,created,json.dumps(detail,ensure_ascii=False)))
        if result.rowcount:
            for device in auth.DB.execute('SELECT id FROM alert_devices WHERE user_id=?', (user['id'],)):
                auth.DB.execute("INSERT OR IGNORE INTO alert_deliveries VALUES(?,?,'pending',0,?,'')", (result.lastrowid,device['id'],self.clock()))
        return result.rowcount

    def register(self, user, body):
        device = device_id(body.get('device'))
        sub = subscription(body.get('subscription'))
        with auth.LOCK:
            old = auth.DB.execute('SELECT * FROM alert_devices WHERE id=?', (device,)).fetchone()
            if old and old['user_id'] != user['id']: raise auth.Forbidden('Este dispositivo pertenece a otra sesión; cierra sesión primero')
            if not old and auth.DB.execute('SELECT COUNT(*) FROM alert_devices WHERE user_id=?',(user['id'],)).fetchone()[0]>=20:
                raise ValueError('Límite de 20 dispositivos de avisos; desactiva uno antes de añadir otro')
            if sub:
                endpoint = sub['endpoint']
                for row in auth.DB.execute('SELECT id,user_id,subscription FROM alert_devices WHERE subscription IS NOT NULL'):
                    if json.loads(row['subscription'])['endpoint'] == endpoint and row['id'] != device:
                        raise ValueError('Este navegador ya tiene otro dispositivo de avisos; desactívalo antes de activar otro')
            auth.DB.execute('INSERT OR REPLACE INTO alert_devices VALUES(?,?,?,?,?)', (device,user['id'],json.dumps(sub) if sub else None,old['created'] if old else self.clock(),self.clock()))
            if sub and (not old or old['subscription']!=json.dumps(sub)):
                auth.DB.execute("UPDATE alert_deliveries SET status='pending',attempts=0,due=?,error='' WHERE device=? AND status='failed' AND alert_id IN (SELECT id FROM alerts WHERE read_at IS NULL AND created>?)",(self.clock(),device,self.clock()-3600))
            auth.DB.commit()
        return {'ok':True,'push':bool(sub),'public_key':self.public_key}

    def disconnect(self, user, device):
        device_id(device)
        with auth.LOCK:
            row = auth.DB.execute('SELECT user_id FROM alert_devices WHERE id=?', (device,)).fetchone()
            if row and row['user_id'] != user['id']: raise auth.Forbidden('Dispositivo ajeno')
            auth.DB.execute('DELETE FROM alert_deliveries WHERE device=?', (device,))
            auth.DB.execute('DELETE FROM alert_devices WHERE id=?', (device,));auth.DB.commit()
        return {'ok':True}

    def snapshot(self, user, device=None):
        with auth.LOCK:
            items = [dict(r) for r in auth.DB.execute('SELECT * FROM alerts WHERE user_id=? ORDER BY id DESC', (user['id'],)) if self.visible(user, r)]
            unread = sum(i['kind'] == 'blocked' and i['read_at'] is None for i in items)
            requests = auth.requests_for(user)
            pending = sum(r['status'] == 'pending' for r in requests)
            found = auth.DB.execute('SELECT * FROM alert_devices WHERE id=? AND user_id=?', (device,user['id'])).fetchone() if device else None
            candidates, diagnostic = [], {'registered':bool(found),'push':bool(found and found['subscription'])}
            if found:
                for item in items:
                    delivery = auth.DB.execute('SELECT * FROM alert_deliveries WHERE alert_id=? AND device=?', (item['id'],device)).fetchone()
                    if delivery and self.current(user,item) and item['read_at'] is None and delivery['status'] in ('pending','retry','sending') and delivery['due'] <= self.clock() and item['created'] > self.clock()-3600:
                        candidates.append(self.public(item))
                last = auth.DB.execute('SELECT status,attempts,error,due FROM alert_deliveries WHERE device=? ORDER BY alert_id DESC LIMIT 1', (device,)).fetchone()
                if last: diagnostic['last_delivery'] = dict(last)
            scan = auth.DB.execute('SELECT value FROM alert_meta WHERE key=?',('scan:'+str(user['id']),)).fetchone()
            diagnostic['scan'] = json.loads(scan[0]) if scan else {'status':'Todavía no se han recogido avisos para esta cuenta.'}
            return {'items':[self.public(i) for i in items[:200]],'unread':unread,'pending_requests':pending,'badge':unread+pending,'requests':requests,'deliveries':candidates[:20], 'diagnostic':diagnostic,'public_key':self.public_key}

    def public(self, item):
        detail = json.loads(item['detail'])
        target = {'kind':'request','id':detail['request_id']} if item['kind']=='request' else {'kind':'client','client':item['client'],'service':item['service']}
        target['alert_id'] = item['id']
        if item['kind']=='test': target=None
        return {k:item[k] for k in ('id','kind','client','service','created','read_at')} | {'detail':detail,'target':target}

    def read(self, user, body):
        identifier = body.get('id')
        if identifier is not None and (type(identifier) is not int or identifier<=0): raise ValueError('Aviso inválido')
        with auth.LOCK:
            items = [dict(r) for r in auth.DB.execute('SELECT * FROM alerts WHERE user_id=?', (user['id'],)) if self.visible(user,r)]
            if identifier is not None and not any(i['id']==identifier for i in items): raise auth.Forbidden('Aviso no disponible para esta cuenta')
            for item in items:
                if identifier is None or item['id']==identifier:
                    auth.DB.execute('UPDATE alerts SET read_at=COALESCE(read_at,?) WHERE id=?', (self.clock(),item['id']))
            auth.DB.commit()
        return {'ok':True}

    def delivery(self, user, body):
        device, identifier, action = device_id(body.get('device')), body.get('id'), body.get('status')
        if type(identifier) is not int or identifier<=0 or action not in ('claim','accepted','failed'): raise ValueError('Resultado de aviso inválido')
        with auth.LOCK:
            found = auth.DB.execute('SELECT * FROM alert_devices WHERE id=? AND user_id=?', (device,user['id'])).fetchone()
            item = auth.DB.execute('SELECT * FROM alerts WHERE id=? AND user_id=?', (identifier,user['id'])).fetchone()
            if not found or not item or not self.current(user,item) or found['subscription']: raise auth.Forbidden('Entrega no disponible para esta cuenta o canal')
            job = auth.DB.execute('SELECT * FROM alert_deliveries WHERE alert_id=? AND device=?', (identifier,device)).fetchone()
            if not job: raise ValueError('Entrega desconocida')
            if action == 'claim':
                if item['read_at'] is not None or job['status'] not in ('pending','retry','sending') or job['due']>self.clock() or job['attempts']>=5: return {'claimed':False}
                auth.DB.execute("UPDATE alert_deliveries SET status='sending',attempts=attempts+1,due=? WHERE alert_id=? AND device=?", (self.clock()+60,identifier,device))
            else:
                if job['status'] != 'sending': return {'ok':True}
                self.finish(identifier,device,action=='accepted',job['attempts'],'browser_rejected')
            auth.DB.commit()
        return {'claimed':True} if action=='claim' else {'ok':True}

    def finish(self, identifier, device, accepted, attempts, error):
        status = 'accepted' if accepted else 'failed' if attempts>=5 else 'retry'
        auth.DB.execute('UPDATE alert_deliveries SET status=?,due=?,error=? WHERE alert_id=? AND device=?', (status,self.clock()+min(300,10*2**attempts),'' if accepted else error,identifier,device))

    def payload(self, user, item):
        value = self.public(item)
        title = 'Nueva solicitud de '+value['detail']['username'] if item['kind']=='request' else item['client']+' · '+item['service']
        body = item['client']+' · '+str(value['detail']['minutes'])+' minutos' if item['kind']=='request' else 'Servicio bloqueado. Pulsa para revisar y autorizar tiempo.'
        if item['kind']=='test': title,body='Parental · Prueba desde el servidor','Este aviso se ha enviado desde Docker mediante Web Push.'
        return {'title':title,'body':body,'target':value['target'],'tag':'parental-alert-'+str(item['id']),'badge_count':self.snapshot(user)['badge']}

    def test(self, user, body):
        auth.require(user,'admin','responsable')
        device=device_id(body.get('device'))
        with auth.LOCK:
            row=auth.DB.execute('SELECT * FROM alert_devices WHERE id=? AND user_id=? AND subscription IS NOT NULL',(device,user['id'])).fetchone()
            if not row: raise ValueError('Activa primero Push en este dispositivo')
            identifier=auth.DB.execute("INSERT INTO alerts(user_id,source,kind,client,service,created,detail) VALUES(?,?,'test','','',?,'{}')",(user['id'],'test:'+str(time.time_ns()),self.clock())).lastrowid
            auth.DB.execute("INSERT INTO alert_deliveries VALUES(?,?,'pending',0,?,'')",(identifier,device,self.clock()+10))
            auth.DB.commit()
        return {'ok':True}

    def send(self, sub, payload):
        from pywebpush import webpush
        import requests
        class NoRedirectSession(requests.Session):
            def request(self,*args,**kwargs):
                kwargs['allow_redirects']=False
                return super().request(*args,**kwargs)
        with NoRedirectSession() as session:
            response = webpush(subscription_info=sub,data=json.dumps(payload,ensure_ascii=False),vapid_private_key=str(self.keyfile),vapid_claims={'sub':os.getenv('WEB_PUSH_CONTACT','mailto:admin@parental.local')},ttl=3600,timeout=10,requests_session=session)
            if response.status_code not in (200,201,202): raise ValueError('push_provider_rejected')

    def dispatch(self):
        # Send outside the shared database/AdGuard locks. Never log endpoint, keys or response bodies.
        for _ in range(20):
            with auth.LOCK:
                jobs = auth.DB.execute("SELECT j.*,d.user_id,d.subscription FROM alert_deliveries j JOIN alert_devices d ON d.id=j.device WHERE d.subscription IS NOT NULL AND j.status IN ('pending','retry','sending') AND j.due<=? ORDER BY j.alert_id LIMIT 50", (self.clock(),)).fetchall()
                job = None
                for candidate in jobs:
                    item = auth.DB.execute('SELECT * FROM alerts WHERE id=?', (candidate['alert_id'],)).fetchone()
                    user = self.user(candidate['user_id'])
                    if not item or item['user_id']!=candidate['user_id'] or item['read_at'] is not None or not self.current(user,item) or item['created']<self.clock()-3600 or candidate['attempts']>=5:
                        auth.DB.execute("UPDATE alert_deliveries SET status='skipped' WHERE alert_id=? AND device=?", (candidate['alert_id'],candidate['device']))
                        continue
                    job = candidate; break
                if not job: auth.DB.commit();return
                attempts = job['attempts']+1
                auth.DB.execute("UPDATE alert_deliveries SET status='sending',attempts=?,due=? WHERE alert_id=? AND device=?", (attempts,self.clock()+60,job['alert_id'],job['device']))
                payload = self.payload(user,item);auth.DB.commit()
            accepted, code = False, None
            try: self.sender(json.loads(job['subscription']),payload);accepted=True
            except Exception as error:
                response = getattr(error,'response',None)
                code = getattr(response,'status_code',None)
            with auth.LOCK:
                self.finish(job['alert_id'],job['device'],accepted,attempts,'push_provider_'+str(code) if code else 'push_network_or_configuration')
                if code in (404,410):
                    auth.DB.execute('UPDATE alert_devices SET subscription=NULL WHERE id=?', (job['device'],))
                    auth.DB.execute("UPDATE alert_deliveries SET status='failed',error='push_subscription_expired' WHERE device=? AND status!='accepted'", (job['device'],))
                auth.DB.commit()
