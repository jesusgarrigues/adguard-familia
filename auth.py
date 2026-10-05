"""Local accounts, scoped permissions, sessions and approval requests."""
import hashlib, hmac, json, secrets, sqlite3, threading, time
from pathlib import Path

ROLES={'admin','responsable','solicitante','observador'}
AVATARS=('', *(f'face-{n:02d}' for n in range(1,13)))
LOCK=threading.RLock()
DB=None

class Forbidden(PermissionError): pass


def init(folder):
    global DB
    DB=sqlite3.connect(Path(folder)/'accounts.db',check_same_thread=False)
    DB.row_factory=sqlite3.Row
    DB.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT, clients TEXT, edit_policy INTEGER, max_minutes INTEGER, active INTEGER);
    CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER,csrf TEXT,expires REAL);
    CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY,user_id INTEGER,client TEXT,service TEXT,minutes INTEGER,reason TEXT,status TEXT,created REAL,reviewer INTEGER,reviewed REAL,approved_minutes INTEGER);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,time REAL,user_id INTEGER,action TEXT,detail TEXT);
    CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER,until REAL);''')
    columns={row['name'] for row in DB.execute('PRAGMA table_info(requests)')}
    if 'extend_bedtime' not in columns: DB.execute('ALTER TABLE requests ADD COLUMN extend_bedtime INTEGER NOT NULL DEFAULT 0')
    if 'approved_extend_bedtime' not in columns: DB.execute('ALTER TABLE requests ADD COLUMN approved_extend_bedtime INTEGER')
    if 'avatar' not in {row['name'] for row in DB.execute('PRAGMA table_info(users)')}:
        DB.execute("ALTER TABLE users ADD COLUMN avatar TEXT NOT NULL DEFAULT ''")
    DB.commit()


def password_hash(password):
    if not isinstance(password,str) or len(password)<12 or len(password)>512: raise ValueError('La contraseña debe tener entre 12 y 512 caracteres')
    salt=secrets.token_hex(16)
    digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return salt+':'+digest


def verify(password,stored):
    salt,digest=stored.split(':')
    return hmac.compare_digest(hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex(),digest)


def public(row):
    d=dict(row)
    d.pop('password',None)
    d['clients']=json.loads(d['clients']);d['edit_policy']=bool(d['edit_policy']);d['active']=bool(d['active'])
    return d


def configured(): return DB.execute('SELECT 1 FROM users LIMIT 1').fetchone() is not None


def audit(user,action,detail):
    DB.execute('INSERT INTO audit(time,user_id,action,detail) VALUES(?,?,?,?)',(time.time(),user['id'] if user else None,action,json.dumps(detail,ensure_ascii=False)))
    DB.execute('DELETE FROM audit WHERE id NOT IN (SELECT id FROM audit ORDER BY id DESC LIMIT 5000)');DB.commit()


def bootstrap(token,expected,username,password):
    with LOCK:
        if configured(): raise Forbidden('El administrador inicial ya está creado')
        if not expected or not hmac.compare_digest(str(token),expected): raise Forbidden('La clave inicial APP_TOKEN es incorrecta')
        return save_user(None,{'username':username,'password':password,'role':'admin','clients':[],'edit_policy':True,'max_minutes':1440,'active':True},bootstrap=True)


def save_user(actor,body,bootstrap=False):
    if not bootstrap: require(actor,'admin')
    with LOCK:
        uid=body.get('id');old=DB.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone() if uid else None
        if uid and not old: raise ValueError('Usuario desconocido')
        name=body.get('username',old['username'] if old else '').strip().lower()
        role=body.get('role',old['role'] if old else 'solicitante')
        clients=body.get('clients',json.loads(old['clients']) if old else [])
        duration=body.get('max_minutes',old['max_minutes'] if old else 120)
        edit=body.get('edit_policy',bool(old['edit_policy']) if old else False)
        active=body.get('active',bool(old['active']) if old else True)
        avatar=body.get('avatar',old['avatar'] if old else '')
        if not isinstance(avatar,str) or avatar not in AVATARS: raise ValueError('Selecciona una cara del catálogo')
        if not name or len(name)>80 or role not in ROLES: raise ValueError('Usuario o rol inválido')
        if not isinstance(clients,list) or any(not isinstance(x,str) or not x for x in clients): raise ValueError('Asignación de clientes inválida')
        if type(duration) is not int or not 1<=duration<=1440 or type(edit) is not bool or type(active) is not bool: raise ValueError('Permisos inválidos')
        if old and old['role']=='admin' and old['active'] and (role!='admin' or not active):
            if DB.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]<=1: raise ValueError('Debe permanecer al menos un administrador activo')
        pwd=password_hash(body['password']) if body.get('password') else old['password'] if old else None
        if not pwd: raise ValueError('Contraseña obligatoria')
        try:
            if old: DB.execute('UPDATE users SET username=?,password=?,role=?,clients=?,edit_policy=?,max_minutes=?,active=?,avatar=? WHERE id=?',(name,pwd,role,json.dumps(clients),int(edit),duration,int(active),avatar,uid))
            else: uid=DB.execute('INSERT INTO users(username,password,role,clients,edit_policy,max_minutes,active,avatar) VALUES(?,?,?,?,?,?,?,?)',(name,pwd,role,json.dumps(clients),int(edit),duration,int(active),avatar)).lastrowid
        except sqlite3.IntegrityError: raise ValueError('Ese nombre de usuario ya existe')
        if old and (name!=old['username'] or pwd!=old['password'] or role!=old['role'] or clients!=json.loads(old['clients']) or edit!=bool(old['edit_policy']) or duration!=old['max_minutes'] or active!=bool(old['active'])):
            DB.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
        DB.commit();audit(actor,'user_saved',{'id':uid,'role':role,'clients':clients,'active':active})
        return public(DB.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())


def save_avatar(actor,body):
    if not actor: raise Forbidden('Inicia sesión para continuar')
    if set(body)-{'avatar','user_id'}: raise ValueError('Solo puedes cambiar la cara desde este formulario')
    uid=body.get('user_id',actor['id'])
    if type(uid) is not int: raise ValueError('Usuario inválido')
    if uid!=actor['id']: require(actor,'admin')
    avatar=body.get('avatar')
    if not isinstance(avatar,str) or avatar not in AVATARS: raise ValueError('Selecciona una cara del catálogo')
    with LOCK:
        if not DB.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone(): raise ValueError('Usuario desconocido')
        DB.execute('UPDATE users SET avatar=? WHERE id=?',(avatar,uid));DB.commit()
        audit(actor,'avatar_saved',{'user_id':uid,'avatar':avatar})
        return public(DB.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())


def login(username,password,ip):
    if not isinstance(username,str) or not isinstance(password,str) or len(password)>512: raise Forbidden('Credenciales incorrectas')
    with LOCK:
        now=time.time();key=hashlib.sha256((ip+'|'+username.lower()).encode()).hexdigest()
        attempt=DB.execute('SELECT * FROM attempts WHERE key=?',(key,)).fetchone()
        if attempt and attempt['until']>now and attempt['count']>=5: raise Forbidden('Demasiados intentos. Espera 15 minutos')
        row=DB.execute('SELECT * FROM users WHERE username=?',(username.strip().lower(),)).fetchone()
        if not row or not row['active'] or not verify(password,row['password']):
            count=attempt['count']+1 if attempt and attempt['until']>now else 1
            DB.execute('INSERT OR REPLACE INTO attempts VALUES(?,?,?)',(key,count,now+900));DB.commit();raise Forbidden('Credenciales incorrectas')
        DB.execute('DELETE FROM attempts WHERE key=?',(key,));DB.execute('DELETE FROM sessions WHERE expires<?',(now,))
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
        DB.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['id'],csrf,now+43200));DB.commit()
        audit(public(row),'login',{})
        return token,csrf,public(row)


def session(token):
    with LOCK:
        row=DB.execute('SELECT u.*,s.csrf FROM sessions s JOIN users u ON s.user_id=u.id WHERE s.token=? AND s.expires>? AND u.active=1',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        if not row: return None
        result=public(row);return result


def logout(token):
    with LOCK: DB.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(token.encode()).hexdigest(),));DB.commit()


def require(user,*roles):
    if not user or user['role'] not in roles: raise Forbidden('Tu rol no permite esta operación')


def scoped(user,client):
    if user['role']!='admin' and client not in user['clients']: raise Forbidden('No tienes acceso a este cliente')


def grant(user,client,minutes=None,edit=False):
    require(user,'admin','responsable');scoped(user,client)
    if edit and user['role']!='admin' and not user['edit_policy']: raise Forbidden('No tienes permiso para editar restricciones permanentes')
    if minutes is not None and (type(minutes) is not int or not 1<=minutes<=user['max_minutes']): raise ValueError('La duración supera tu límite de '+str(user['max_minutes'])+' minutos')


def bedtime_option(body,client):
    value=body.get('extend_bedtime',False)
    if type(value) is not bool: raise ValueError('La opción de ampliar el horario de descanso debe ser booleana')
    if value and not client.startswith('nintendo:'): raise ValueError('La ampliación del horario de descanso solo se admite para Nintendo')
    return value


def request_access(user,body,validate):
    require(user,'solicitante');client,service,minutes=body['client'],body['service'],body['minutes'];scoped(user,client)
    if type(minutes) is not int or not 1<=minutes<=1440: raise ValueError('Duración inválida')
    extend_bedtime=bedtime_option(body,client)
    reason=body.get('reason','')
    if not isinstance(reason,str) or len(reason)>1000: raise ValueError('Motivo demasiado largo')
    validate(client,service)
    with LOCK:
        if DB.execute("SELECT 1 FROM requests WHERE user_id=? AND client=? AND service=? AND status='pending'",(user['id'],client,service)).fetchone(): raise ValueError('Ya tienes una solicitud pendiente para esta restricción')
        rid=DB.execute("INSERT INTO requests(user_id,client,service,minutes,reason,status,created,extend_bedtime) VALUES(?,?,?,?,?,'pending',?,?)",(user['id'],client,service,minutes,reason,time.time(),int(extend_bedtime))).lastrowid
        DB.commit();audit(user,'request_created',{'id':rid,'client':client,'service':service,'minutes':minutes,'extend_bedtime':extend_bedtime});return rid


def requests_for(user):
    with LOCK:
        DB.execute("UPDATE requests SET status='expired' WHERE status='pending' AND created<?",(time.time()-86400,));DB.commit()
        rows=[dict(r) for r in DB.execute('SELECT r.*,u.username,u.avatar FROM requests r JOIN users u ON r.user_id=u.id ORDER BY r.id DESC LIMIT 1000')]
        for row in rows:
            row['extend_bedtime']=bool(row['extend_bedtime'])
            row['approved_extend_bedtime']=None if row['approved_extend_bedtime'] is None else bool(row['approved_extend_bedtime'])
    return [r for r in rows if user['role']=='admin' or (r['user_id']==user['id'] if user['role']=='solicitante' else r['client'] in user['clients'])]


def review(user,body,permit):
    require(user,'admin','responsable')
    if type(body.get('id')) is not int or body['id']<=0: raise ValueError('Identificador de solicitud inválido')
    with LOCK:
        row=DB.execute('SELECT * FROM requests WHERE id=?',(body['id'],)).fetchone()
        if not row: raise ValueError('Solicitud desconocida')
        grant(user,row['client']);decision=body['decision']
        if row['status']!='pending': raise ValueError('La solicitud ya se ha resuelto')
        if row['created']<time.time()-86400: raise ValueError('La solicitud ha caducado')
        if decision not in ('approve','reject'): raise ValueError('Decisión inválida')
        extend_bedtime=bedtime_option(body,row['client'])
        minutes=body.get('minutes',row['minutes'])
        if decision=='approve':
            grant(user,row['client'],minutes)
            if row['client'].startswith('nintendo:') and minutes not in (5,10,15,20,25,30,40,60): raise ValueError('Selecciona 5, 10, 15, 20, 25, 30, 40 o 60 minutos de tiempo extra')
            # Persist approval before remote writes. Nintendo grants must not be replayed.
            approved_bedtime=int(extend_bedtime) if row['client'].startswith('nintendo:') else None
            DB.execute("UPDATE requests SET status='approved_pending',reviewer=?,reviewed=?,approved_minutes=?,approved_extend_bedtime=? WHERE id=?",(user['id'],time.time(),minutes,approved_bedtime,row['id']));DB.commit()
            audit(user,'request_approved',{'id':row['id'],'client':row['client'],'minutes':minutes,'requested_extend_bedtime':bool(row['extend_bedtime']),'approved_extend_bedtime':extend_bedtime if approved_bedtime is not None else None})
            try:
                result=permit(row['client'],row['service'],minutes,extend_bedtime=extend_bedtime) if approved_bedtime is not None else permit(row['client'],row['service'],minutes)
                status='approval_error' if isinstance(result,dict) and result.get('status')=='failed' else 'approval_closed' if isinstance(result,dict) and result.get('status')=='superseded' else 'approved_pending' if isinstance(result,dict) and result.get('status')=='pending' else 'approved'
                DB.execute('UPDATE requests SET status=? WHERE id=?',(status,row['id']));DB.commit()
                return result
            except Exception:
                DB.execute("UPDATE requests SET status='approval_error' WHERE id=?",(row['id'],));DB.commit()
                raise
        else:
            DB.execute("UPDATE requests SET status='rejected',reviewer=?,reviewed=? WHERE id=?",(user['id'],time.time(),row['id']));DB.commit();audit(user,'request_rejected',{'id':row['id']})


def withdraw(user,rid):
    require(user,'solicitante')
    if type(rid) is not int or rid<=0: raise ValueError('Identificador de solicitud inválido')
    with LOCK:
        row=DB.execute('SELECT * FROM requests WHERE id=?',(rid,)).fetchone()
        if not row or row['user_id']!=user['id']: raise Forbidden('Esta solicitud no te pertenece')
        if row['status']!='pending': raise ValueError('La solicitud ya se ha resuelto')
        DB.execute("UPDATE requests SET status='withdrawn' WHERE id=?",(rid,));DB.commit();audit(user,'request_withdrawn',{'id':rid})
