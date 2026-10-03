"""End-to-end HTTP smoke test for CI, using a local simulated AdGuard."""
import http.cookiejar, json, os, secrets, subprocess, tempfile, time, urllib.error, urllib.request
from pathlib import Path

initial=secrets.token_urlsafe(32)
env=dict(os.environ,DATA_DIR=tempfile.mkdtemp(),DEMO='true',APP_TOKEN=initial)
process=subprocess.Popen(['python','app.py'],env=env)

class Client:
    def __init__(self): self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));self.csrf=''
    def call(self,path,body=None,expected=200):
        headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf}
        req=urllib.request.Request('http://127.0.0.1:8080/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with self.opener.open(req,timeout=5) as response: code=response.status;data=json.load(response)
        except urllib.error.HTTPError as e:code=e.code;data=json.load(e)
        assert code==expected,(path,code,data)
        if 'csrf' in data:self.csrf=data['csrf']
        return data

try:
    admin=Client()
    for _ in range(50):
        try:admin.call('auth/status');break
        except OSError:time.sleep(.1)
    else:raise RuntimeError('App did not start')
    admin.call('auth/setup',{'token':initial,'username':'admin','password':'admin-password-1234'})
    for name,role in [('emma','solicitante'),('parent','responsable'),('observer','observador')]:admin.call('users',{'username':name,'password':name+'-password-1234','role':role,'clients':['iMac de Emma'],'max_minutes':60})
    child=Client();child.call('auth/login',{'username':'emma','password':'emma-password-1234'})
    state=child.call('state');assert [c['name'] for c in state['clients']]==['iMac de Emma'];assert state['events']==[];assert state['server']=={}
    child.call('permit',{'client':'iMac de Emma','service':'youtube','minutes':20},403)
    child.call('global',{'patch':{}},403)
    child.call('request',{'client':'iMac de Martín','service':'youtube','minutes':20},403)
    rid=child.call('request',{'client':'iMac de Emma','service':'youtube','minutes':20,'reason':'Vídeo de clase'})['id']
    assert admin.call('state')['leases']==[]
    parent=Client();parent.call('auth/login',{'username':'parent','password':'parent-password-1234'})
    parent.call('request/review',{'id':rid,'decision':'approve','minutes':15})
    granted=child.call('state');assert len(granted['leases'])==1;assert granted['requests'][0]['status']=='approved'
    observer=Client();observer.call('auth/login',{'username':'observer','password':'observer-password-1234'})
    observer.call('cancel',{'client':'iMac de Emma','service':'youtube'},403)
    parent.call('client',{'client':'iMac de Emma','patch':{'parental_enabled':False}},403)
    for path in ('manifest.webmanifest','sw.js','icon-192.png','icon-512.png'):
        with urllib.request.urlopen('http://127.0.0.1:8080/'+path) as response:assert response.status==200
    child.call('auth/logout',{});child.call('me',expected=401)
    print('HTTP smoke passed: bootstrap, accounts, scoped roles, mandatory approval, session logout and PWA assets')
finally:process.terminate();process.wait(timeout=5)
