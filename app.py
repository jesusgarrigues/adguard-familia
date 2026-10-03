import logging, socket, ssl
from collections import deque
import base64, copy, hmac, ipaddress, json, os, sqlite3, threading, time, urllib.error, urllib.request
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent
DATA = Path(os.getenv('DATA_DIR', '/data'))
DATA.mkdir(parents=True, exist_ok=True)
TOKEN = os.environ.get('APP_TOKEN', '')
LOCK = threading.RLock()
DB = sqlite3.connect(DATA / 'state.db', check_same_thread=False)
DB.executescript('''CREATE TABLE IF NOT EXISTS leases (client TEXT, service TEXT, expires REAL, PRIMARY KEY(client,service));
CREATE TABLE IF NOT EXISTS baselines (client TEXT PRIMARY KEY, config TEXT);
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, time REAL, client TEXT, service TEXT, domain TEXT, kind TEXT);
CREATE TABLE IF NOT EXISTS seen (key TEXT PRIMARY KEY, time REAL);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
''')
LAST_ERROR = ''
DIAGNOSTICS = deque(maxlen=100)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
SAFE_KEYS = ('enabled','bing','duckduckgo','ecosia','google','pixabay','yandex','youtube')
BOOL_KEYS = ('use_global_settings','filtering_enabled','parental_enabled','safebrowsing_enabled','safesearch_enabled','use_global_blocked_services','ignore_querylog','ignore_statistics','upstreams_cache_enabled')
CLIENT_KEYS = set(BOOL_KEYS) | {'name','ids','safe_search','blocked_services_schedule','blocked_services','upstreams','tags','upstreams_cache_size'}
RESTRICTIONS = {'@filtering':'filtering_enabled','@parental':'parental_enabled','@safebrowsing':'safebrowsing_enabled','@safesearch':'safe_search'}
POLICY_KEYS = ('use_global_settings','filtering_enabled','parental_enabled','safebrowsing_enabled','safe_search','safesearch_enabled','use_global_blocked_services','blocked_services','blocked_services_schedule')


def demo_reset():
    global DEMO_CLIENTS, DEMO_GLOBAL
    defaults = dict(use_global_settings=True,filtering_enabled=True,parental_enabled=True,safebrowsing_enabled=True,safe_search={k:True for k in SAFE_KEYS},use_global_blocked_services=True,blocked_services=[],blocked_services_schedule={'time_zone':'Local'},upstreams=[],tags=[],ignore_querylog=False,ignore_statistics=False,upstreams_cache_enabled=False,upstreams_cache_size=0)
    DEMO_CLIENTS = [dict(copy.deepcopy(defaults),name='iMac de Emma',ids=['192.168.1.20']),dict(copy.deepcopy(defaults),name='iMac de Martín',ids=['192.168.1.21'])]
    DEMO_GLOBAL = {'filtering_enabled':True,'parental_enabled':True,'safebrowsing_enabled':True,'safe_search':{k:True for k in SAFE_KEYS},'blocked_services':{'ids':['youtube','tiktok'],'schedule':{'time_zone':'Local'}},'protection_enabled':True}


demo_reset()


def server_config():
    saved = DB.execute("SELECT value FROM settings WHERE key='server'").fetchone()
    return json.loads(saved[0]) if saved else {'url':os.getenv('ADGUARD_URL',''),'username':os.getenv('ADGUARD_USER',''),'password':os.getenv('ADGUARD_PASSWORD',''),'demo':os.getenv('DEMO','false').lower()=='true'}


def public_server():
    c = server_config()
    return {k:v for k,v in c.items() if k != 'password'} | {'has_password':bool(c.get('password'))}


class AdGuardError(RuntimeError):
    def __init__(self, endpoint, category, message, status=None):
        self.detail = {'endpoint': endpoint.split('?')[0], 'category': category, 'message': message, 'http_status': status}
        super().__init__(message)


def diagnostic(endpoint, ok, started, error=None):
    item = {'time': time.time(), 'endpoint': endpoint.split('?')[0], 'ok': ok, 'duration_ms': round((time.monotonic()-started)*1000)}
    if error: item.update(error.detail)
    DIAGNOSTICS.append(item)
    if error: logging.warning('AdGuard endpoint=%s category=%s status=%s: %s', item['endpoint'], item['category'], item.get('http_status'), item['message'])


def network_error(endpoint, error):
    reason = getattr(error, 'reason', error)
    if isinstance(error, urllib.error.HTTPError):
        code=error.code
        message={401:'AdGuard rechaza el usuario o contraseña (HTTP 401).',403:'Acceso denegado por AdGuard o su proxy (HTTP 403).',404:'No se encuentra la API (HTTP 404). Comprueba URL, puerto y ruta del proxy.'}.get(code, 'AdGuard o su proxy devolvió HTTP '+str(code)+'.')
        return AdGuardError(endpoint,'http',message,code)
    if isinstance(reason, ssl.SSLCertVerificationError): return AdGuardError(endpoint,'tls','No se puede verificar el certificado HTTPS. Usa un certificado confiable o instala su CA en el contenedor.')
    if isinstance(reason, (TimeoutError,socket.timeout)): return AdGuardError(endpoint,'timeout','La conexión ha superado 10 segundos. Comprueba red, IP, puerto y firewall desde el contenedor.')
    if isinstance(reason, socket.gaierror): return AdGuardError(endpoint,'dns','No se puede resolver el nombre del servidor desde el contenedor.')
    if isinstance(reason, ConnectionRefusedError): return AdGuardError(endpoint,'connection_refused','El servidor rechaza la conexión. Comprueba el puerto web de AdGuard.')
    return AdGuardError(endpoint,'network','No se puede alcanzar el servidor desde el contenedor. Comprueba IP, puerto, red Docker y firewall.')


def api(path, payload=None, method=None, config=None):
    cfg = config or server_config()
    if cfg.get('demo'):
        if path == 'clients': return {'clients':copy.deepcopy(DEMO_CLIENTS),'auto_clients':[{'name':'Tablet invitada','ip':'192.168.1.50','source':'rdns'}],'supported_tags':['device_pc','device_phone','user_child']}
        if path == 'status': return {'version':'demo','protection_enabled':DEMO_GLOBAL['protection_enabled']}
        if path == 'blocked_services/all': return {'blocked_services':[{'id':s,'name':n} for s,n in [('youtube','YouTube'),('tiktok','TikTok'),('twitch','Twitch'),('facebook','Facebook'),('instagram','Instagram'),('netflix','Netflix'),('discord','Discord')]]}
        if path == 'blocked_services/get': return copy.deepcopy(DEMO_GLOBAL['blocked_services'])
        if path == 'blocked_services/update': DEMO_GLOBAL['blocked_services']=copy.deepcopy(payload); return {}
        if path == 'filtering/status': return {'enabled':DEMO_GLOBAL['filtering_enabled'],'interval':24}
        if path == 'filtering/config': DEMO_GLOBAL['filtering_enabled']=payload['enabled']; return {}
        if path == 'safesearch/status': return copy.deepcopy(DEMO_GLOBAL['safe_search'])
        if path == 'safesearch/settings': DEMO_GLOBAL['safe_search']=copy.deepcopy(payload); return {}
        for category, field in [('parental','parental_enabled'),('safebrowsing','safebrowsing_enabled')]:
            if path==category+'/status': return {'enabled':DEMO_GLOBAL[field]}
            if path in (category+'/enable',category+'/disable'): DEMO_GLOBAL[field]=path.endswith('/enable');return {}
        if path.startswith('querylog'): return {'data':[]}
        if path == 'clients/update':
            for i,c in enumerate(DEMO_CLIENTS):
                if c['name'] == payload['name']: DEMO_CLIENTS[i] = copy.deepcopy(payload['data']);return {}
            raise ValueError('Cliente desconocido')
        if path == 'clients/add': DEMO_CLIENTS.append(copy.deepcopy(payload));return {}
        raise ValueError('Endpoint no simulado: '+path)
    base = cfg['url'].rstrip('/')
    if not base:
        raise AdGuardError(path,'configuration','Configura la URL del servidor en la pantalla Servidor.')
    url = base + ('/' if base.endswith('/control') else '/control/') + path
    credentials = base64.b64encode((cfg['username']+':'+cfg['password']).encode()).decode()
    req = urllib.request.Request(url, data=json.dumps(payload).encode() if payload is not None else None, method=method or ('POST' if payload is not None else 'GET'),headers={'Authorization':'Basic '+credentials,'Content-Type':'application/json'})
    started=time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw=response.read()
            try: result=json.loads(raw) if raw else {}
            except (ValueError,UnicodeError): raise AdGuardError(path,'response','El servidor devuelve contenido que no es JSON. La URL puede apuntar a una página de login o al puerto equivocado.')
        diagnostic(path,True,started)
        return result
    except AdGuardError as error:
        diagnostic(path,False,started,error)
        raise
    except (urllib.error.URLError,OSError) as error:
        safe=network_error(path,error)
        diagnostic(path,False,started,safe)
        raise safe from None


def global_config():
    return {'filtering_enabled':api('filtering/status')['enabled'],'parental_enabled':api('parental/status')['enabled'],'safebrowsing_enabled':api('safebrowsing/status')['enabled'],'safe_search':api('safesearch/status'),'blocked_services':api('blocked_services/get'),'protection_enabled':api('status')['protection_enabled']}


def effective(client, global_values):
    result = {key:copy.deepcopy(client.get(key,False)) for key in ('filtering_enabled','parental_enabled','safebrowsing_enabled')}
    result['safe_search'] = copy.deepcopy(client.get('safe_search',{'enabled':client.get('safesearch_enabled',False)}))
    if client.get('use_global_settings',True):
        for key in (*result.keys(),): result[key] = copy.deepcopy(global_values[key])
    inherited = client.get('use_global_blocked_services',True)
    result['blocked_services'] = copy.deepcopy(global_values['blocked_services']['ids'] if inherited else client.get('blocked_services',[]))
    result['blocked_services_schedule'] = copy.deepcopy(global_values['blocked_services'].get('schedule',{}) if inherited else client.get('blocked_services_schedule',{}))
    result['protection_enabled'] = global_values['protection_enabled']
    return result


def baseline_for(name):
    row = DB.execute('SELECT config FROM baselines WHERE client=?',(name,)).fetchone()
    if not row: return None
    b = json.loads(row[0])
    if 'base' not in b:  # Upgrade leases created by the first release.
        c = next(c for c in api('clients')['clients'] if c['name']==name)
        base = copy.deepcopy(c)
        base.update(blocked_services=b['blocked_services'],use_global_blocked_services=b['use_global_blocked_services'])
        b = {'base':base,'applied':c}
    return b


def save_baseline(name,b):
    DB.execute('INSERT OR REPLACE INTO baselines VALUES(?,?)',(name,json.dumps(b)))
    DB.commit()


def event(client, service, domain='', kind='blocked'):
    DB.execute('INSERT INTO events(time,client,service,domain,kind) VALUES(?,?,?,?,?)',(time.time(),client,service,domain,kind))
    DB.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 500)')
    DB.commit()


def overlay(current, baseline, active, globals_):
    updated = copy.deepcopy(current)
    base = baseline['base']
    for key in POLICY_KEYS:
        if key in base: updated[key]=copy.deepcopy(base[key])
        else: updated.pop(key,None)
    eff = effective(base,globals_)
    services = {s for s in active if not s.startswith('@')}
    if services:
        updated['use_global_blocked_services']=False
        updated['blocked_services']=sorted(set(eff['blocked_services'])-services)
        updated['blocked_services_schedule']=eff['blocked_services_schedule']
    if any(s in RESTRICTIONS for s in active):
        updated['use_global_settings']=False
        for key in ('filtering_enabled','parental_enabled','safebrowsing_enabled','safe_search'): updated[key]=copy.deepcopy(eff[key])
        for s in active:
            if s not in RESTRICTIONS: continue
            key=RESTRICTIONS[s]
            if key=='safe_search': updated[key]['enabled']=False;updated['safesearch_enabled']=False
            else: updated[key]=False
    return updated


def reconcile():
    rows = DB.execute('SELECT client FROM baselines').fetchall()
    if not rows: return
    clients = {c['name']:c for c in api('clients')['clients']}
    globals_ = global_config()
    failures=[]
    for (name,) in rows:
        try:
            if name not in clients: raise ValueError('Cliente eliminado o renombrado: '+name)
            b=baseline_for(name)
            current=clients[name]
            # Adopt external policy edits instead of restoring a stale permanent setting.
            for key in POLICY_KEYS:
                if current.get(key)!=b['applied'].get(key) and ('previous' not in b or current.get(key)!=b['previous'].get(key)):
                    if key in current: b['base'][key]=copy.deepcopy(current[key])
                    else: b['base'].pop(key,None)
            active=[r[0] for r in DB.execute('SELECT service FROM leases WHERE client=? AND expires>?',(name,time.time()))]
            updated=overlay(current,b,active,globals_)
            # Record expected result before the remote write: retries remain idempotent.
            previous=copy.deepcopy(b['applied'])
            b['applied']=updated
            save_baseline(name,b)
            try:
                if updated!=current: api('clients/update',{'name':name,'data':updated})
            except Exception:
                # A failed request may have succeeded remotely. Keep both versions as candidates.
                b['previous']=previous
                save_baseline(name,b)
                raise
            b.pop('previous',None)
            save_baseline(name,b)
            if not active:
                DB.execute('DELETE FROM leases WHERE client=?',(name,))
                DB.execute('DELETE FROM baselines WHERE client=?',(name,))
                event(name,'','','restored')
        except Exception as e: failures.append(str(e))
    DB.commit()
    if failures: raise RuntimeError('; '.join(failures))


def permit(name, service, minutes):
    if type(minutes) is not int or not 1 <= minutes <= 1440: raise ValueError('Duración entre 1 y 1440 minutos')
    services={s['id'] for s in api('blocked_services/all')['blocked_services']} | set(RESTRICTIONS)
    if service not in services: raise ValueError('Restricción desconocida')
    clients={c['name']:c for c in api('clients')['clients']}
    if name not in clients: raise ValueError('Da de alta este cliente en AdGuard antes de crear un permiso')
    c=clients[name]
    b=baseline_for(name) or {'base':copy.deepcopy(c),'applied':copy.deepcopy(c)}
    eff=effective(b['base'],global_config())
    enabled=eff['safe_search'].get('enabled',False) if service=='@safesearch' else eff[RESTRICTIONS[service]] if service in RESTRICTIONS else service in eff['blocked_services']
    if not enabled: raise ValueError('Esta restricción no está activada en la configuración base')
    save_baseline(name,b)
    DB.execute('INSERT OR REPLACE INTO leases VALUES(?,?,?)',(name,service,time.time()+minutes*60));DB.commit()
    reconcile()


def validate_schedule(s):
    if not isinstance(s,dict) or set(s)-{'time_zone','sun','mon','tue','wed','thu','fri','sat'}: raise ValueError('Horario inválido')
    zone=s.get('time_zone','Local')
    if zone!='Local':
        try: ZoneInfo(zone)
        except Exception: raise ValueError('Zona horaria inválida')
    for day,r in s.items():
        if day=='time_zone': continue
        if not isinstance(r,dict) or set(r)-{'start','end'}: raise ValueError('Intervalo inválido')
        a,z=r.get('start'),r.get('end')
        if type(a) is not int or type(z) is not int or not 0<=a<z<=86400000 or a%60000 or z%60000: raise ValueError('Intervalo horario inválido')


def validate_client(c):
    if not isinstance(c,dict): raise ValueError('Configuración inválida')
    if not isinstance(c.get('name'),str) or not c['name'].strip(): raise ValueError('Nombre obligatorio')
    if not c.get('ids'): raise ValueError('Indica al menos un identificador')
    for key in BOOL_KEYS:
        if key in c and type(c[key]) is not bool: raise ValueError('Valor inválido: '+key)
    for key in ('ids','upstreams','tags','blocked_services'):
        if key in c and (not isinstance(c[key],list) or any(not isinstance(x,str) or not x for x in c[key])): raise ValueError('Lista inválida: '+key)
    if 'upstreams_cache_size' in c and (type(c['upstreams_cache_size']) is not int or c['upstreams_cache_size']<0): raise ValueError('Caché inválida')
    if 'safe_search' in c: validate_safe(c['safe_search'])
    if 'blocked_services_schedule' in c: validate_schedule(c['blocked_services_schedule'])
    if 'blocked_services' in c: validate_services(c['blocked_services'])


def validate_safe(s):
    if not isinstance(s,dict) or set(s)-set(SAFE_KEYS) or any(type(v) is not bool for v in s.values()): raise ValueError('Búsqueda segura inválida')


def validate_services(ids):
    catalog={s['id'] for s in api('blocked_services/all')['blocked_services']}
    if not isinstance(ids,list) or any(not isinstance(s,str) or s not in catalog for s in ids): raise ValueError('Servicio desconocido')


def save_client(name,patch,add=False):
    if not isinstance(patch,dict) or set(patch)-CLIENT_KEYS: raise ValueError('Campo de cliente no admitido')
    clients=api('clients')['clients']
    current=next((c for c in clients if c['name']==name),None)
    if not add and not current: raise ValueError('Cliente desconocido')
    b=baseline_for(name) if not add else None
    target=copy.deepcopy(b['base'] if b else current or {})
    target.update(patch)
    validate_client(target)
    if any(c['name']==target['name'] and (add or c['name']!=name) for c in clients): raise ValueError('El nombre ya existe')
    if b and target['name']!=name: raise ValueError('Finaliza los permisos activos antes de renombrar el cliente')
    if b:
        nonpolicy=copy.deepcopy(current)
        for key,value in patch.items():
            if key not in POLICY_KEYS: nonpolicy[key]=copy.deepcopy(value)
        if nonpolicy!=current: api('clients/update',{'name':name,'data':nonpolicy})
        b['base']=target
        save_baseline(name,b)
        reconcile()
    else: api('clients/add' if add else 'clients/update',target if add else {'name':name,'data':target})


def save_global(patch):
    allowed={'filtering_enabled','parental_enabled','safebrowsing_enabled','safe_search','blocked_services'}
    if not isinstance(patch,dict) or set(patch)-allowed: raise ValueError('Campo global no admitido')
    for key in ('filtering_enabled','parental_enabled','safebrowsing_enabled'):
        if key in patch and type(patch[key]) is not bool: raise ValueError('Valor global inválido')
    if 'safe_search' in patch: validate_safe(patch['safe_search'])
    if 'blocked_services' in patch:
        value=patch['blocked_services']
        if not isinstance(value,dict) or set(value)-{'ids','schedule'}: raise ValueError('Servicios globales inválidos')
        validate_services(value.get('ids'));validate_schedule(value.get('schedule',{}))
    current=global_config()
    completed=[]
    try:
        for key,value in patch.items():
            if value==current[key]: continue
            if key=='filtering_enabled': api('filtering/config',{'enabled':value,'interval':api('filtering/status')['interval']})
            elif key in ('parental_enabled','safebrowsing_enabled'): api(key.split('_')[0]+('/enable' if value else '/disable'),{})
            elif key=='safe_search': api('safesearch/settings',value,'PUT')
            else: api('blocked_services/update',value,'PUT')
            completed.append(key)
    except Exception as e:
        raise RuntimeError('Guardado global incompleto. Recarga para revisar lo aplicado: '+', '.join(completed)) from e
    reconcile()


def save_server(body,test_only=False):
    if not isinstance(body,dict) or set(body)-{'url','username','password','demo'}: raise ValueError('Servidor inválido')
    old=server_config()
    cfg={k:body.get(k,old.get(k,'')) for k in ('url','username','password','demo')}
    if type(cfg['demo']) is not bool or any(not isinstance(cfg[k],str) for k in ('url','username','password')): raise ValueError('Servidor inválido')
    parsed=urlsplit(cfg['url'])
    if not cfg['demo'] and (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.query or parsed.fragment): raise ValueError('Indica una URL HTTP/HTTPS sin credenciales incrustadas')
    if not test_only and DB.execute('SELECT 1 FROM baselines').fetchone(): raise ValueError('Finaliza todos los permisos antes de cambiar de servidor')
    status=api('status',config=cfg)
    api('clients',config=cfg)
    if test_only:
        for endpoint in ('filtering/status','parental/status','safebrowsing/status','safesearch/status','blocked_services/get','blocked_services/all'):
            api(endpoint,config=cfg)
    if not test_only:
        DB.execute("INSERT OR REPLACE INTO settings VALUES('server',?)",(json.dumps(cfg),))
        DB.execute('DELETE FROM seen');DB.execute('DELETE FROM events');DB.commit()
    return {'ok':True,'version':status.get('version','')}


def client_identity(q, clients):
    info=q.get('client_info') or {}
    if info.get('name'): return info['name']
    value=q.get('client_id') or q.get('client','')
    for c in clients:
        if value in c.get('ids',[]): return c['name']
        for identifier in c.get('ids',[]):
            try:
                if ipaddress.ip_address(q.get('client','')) in ipaddress.ip_network(identifier,strict=False): return c['name']
            except ValueError: pass
    return value or 'Desconocido'


def poll():
    clients=api('clients')['clients']
    reasons={'FilteredSafeBrowsing':'@safebrowsing','FilteredParental':'@parental','SafeSearch':'@safesearch','FilteredBlackList':'@filtering'}
    for q in reversed(api('querylog?limit=500')['data']):
        service=q.get('service_name') if q.get('reason')=='BlockedService' else reasons.get(q.get('reason'))
        if not service: continue
        key=q.get('time','')+'|'+q.get('client','')+'|'+q.get('question',{}).get('name','')+'|'+service
        if DB.execute('SELECT 1 FROM seen WHERE key=?',(key,)).fetchone(): continue
        DB.execute('INSERT INTO seen VALUES(?,?)',(key,time.time()))
        client=client_identity(q,clients)
        recent=DB.execute('SELECT 1 FROM events WHERE client=? AND service=? AND kind=? AND time>?',(client,service,'blocked',time.time()-300)).fetchone()
        if not recent: event(client,service,q.get('question',{}).get('name',''))
    DB.execute('DELETE FROM seen WHERE time<?',(time.time()-86400,));DB.commit()


def state():
    info=api('clients');g=global_config()
    bases={c['name']:(baseline_for(c['name']) or {}).get('base',c) for c in info['clients']}
    return {'clients':info['clients'],'auto_clients':info.get('auto_clients',[]),'supported_tags':info.get('supported_tags',[]),'base_clients':bases,'effective':{c['name']:effective(c,g) for c in info['clients']},'base_effective':{n:effective(c,g) for n,c in bases.items()},'services':api('blocked_services/all')['blocked_services'],'global_config':g,'leases':[dict(zip(('client','service','expires'),r)) for r in DB.execute('SELECT * FROM leases')],'events':[dict(zip(('id','time','client','service','domain','kind'),r)) for r in DB.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')],'error':LAST_ERROR,'server':public_server(),'demo':server_config()['demo']}


def worker():
    global LAST_ERROR
    while True:
        with LOCK:
            try: reconcile();poll();LAST_ERROR=''
            except AdGuardError as e: LAST_ERROR=str(e)
            except Exception: LAST_ERROR='Fallo al sincronizar AdGuard. Revisa el diagnóstico del servidor.';logging.error('Error interno de sincronización (sin datos de credenciales)')
        time.sleep(10)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def respond(self,status,data,mime='application/json'):
        content=json.dumps(data,ensure_ascii=False).encode() if mime=='application/json' else data
        try:
            self.send_response(status);self.send_header('Content-Type',mime+'; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(content)
        except (BrokenPipeError,ConnectionResetError):
            logging.info('El navegador o proxy cerró la solicitud antes de recibir la respuesta')
    def authorized(self): return bool(TOKEN) and hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+TOKEN)
    def do_GET(self):
        if self.path=='/': return self.respond(200,(ROOT/'index.html').read_bytes(),'text/html')
        if not self.authorized(): return self.respond(401,{'error':'Clave de acceso incorrecta'})
        if self.path=='/api/diagnostics': return self.respond(200,{'entries':list(DIAGNOSTICS),'last_error':LAST_ERROR})
        if self.path=='/api/server': return self.respond(200,public_server())
        with LOCK:
            try:
                if self.path=='/api/server': return self.respond(200,public_server())
                if self.path=='/api/diagnostics': return self.respond(200,{'entries':list(DIAGNOSTICS),'last_error':LAST_ERROR})
                if self.path=='/api/state': return self.respond(200,state())
                self.respond(404,{'error':'No encontrado'})
            except AdGuardError as e: self.respond(502,{'error':str(e),'diagnostic':e.detail})
            except Exception: self.respond(502,{'error':'No se puede leer AdGuard. Revisa el diagnóstico en Servidor.'})
    def do_POST(self):
        if not self.authorized(): return self.respond(401,{'error':'Acceso denegado'})
        if self.path=='/api/server/test':
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=131072: raise ValueError('Solicitud inválida')
                self.respond(200,save_server(json.loads(self.rfile.read(length)),True))
            except AdGuardError as e: self.respond(502,{'error':str(e),'diagnostic':e.detail})
            except (ValueError,KeyError,TypeError) as e: self.respond(400,{'error':str(e)})
            except Exception: self.respond(502,{'error':'No se pudo completar el diagnóstico de conexión.'})
            return
        with LOCK:
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=131072: raise ValueError('Solicitud inválida')
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict): raise ValueError('Solicitud inválida')
                result={'ok':True}
                if self.path=='/api/permit': permit(body['client'],body['service'],body['minutes'])
                elif self.path=='/api/cancel':
                    DB.execute('UPDATE leases SET expires=0 WHERE client=? AND service=?',(body['client'],body['service']));DB.commit();reconcile()
                elif self.path=='/api/client': save_client(body['client'],body['patch'])
                elif self.path=='/api/client/add': save_client('',body['patch'],True)
                elif self.path=='/api/global': save_global(body['patch'])
                elif self.path in ('/api/server','/api/server/test'): result=save_server(body,self.path.endswith('/test'))
                else: return self.respond(404,{'error':'No encontrado'})
                self.respond(200,result)
            except AdGuardError as e: self.respond(502,{'error':str(e),'diagnostic':e.detail})
            except (ValueError,KeyError,TypeError) as e: self.respond(400,{'error':str(e)})
            except Exception: self.respond(502,{'error':'AdGuard no confirmó la operación. Recarga para revisar el estado; los permisos temporales pendientes se reintentarán.'})


if __name__=='__main__':
    if len(TOKEN)<16: raise SystemExit('Configura APP_TOKEN con al menos 16 caracteres')
    threading.Thread(target=worker,daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
