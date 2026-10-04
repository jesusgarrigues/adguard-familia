import copy, importlib, os, sqlite3, tempfile, unittest
from unittest.mock import patch
os.environ['DATA_DIR']=tempfile.mkdtemp()
os.environ['DEMO']='true'
import app

class PermissionsTest(unittest.TestCase):
    def setUp(self):
        for table in ('leases','baselines','events','seen','settings','client_appearance'): app.DB.execute('DELETE FROM '+table)
        app.DB.commit();app.demo_reset()
    def expire(self,service=None):
        app.DB.execute('UPDATE leases SET expires=0'+(' WHERE service=?' if service else ''),(service,) if service else ())
        app.DB.commit();app.reconcile()
    def test_expiry_restores_after_reload(self):
        app.permit('iMac de Emma','youtube',20)
        current=copy.deepcopy(app.DEMO_CLIENTS)
        app.DB.execute('UPDATE leases SET expires=0');app.DB.commit()
        app.DB.close();importlib.reload(app);app.DEMO_CLIENTS=current
        app.reconcile()
        self.assertTrue(app.DEMO_CLIENTS[0]['use_global_blocked_services'])
        self.assertEqual(app.DB.execute('SELECT count(*) FROM leases').fetchone()[0],0)
    def test_overlapping_services(self):
        app.permit('iMac de Emma','youtube',20);app.permit('iMac de Emma','tiktok',30)
        self.assertEqual(app.DEMO_CLIENTS[0]['blocked_services'],[])
        self.expire('youtube')
        self.assertEqual(app.DEMO_CLIENTS[0]['blocked_services'],['youtube'])
        self.expire();self.assertTrue(app.DEMO_CLIENTS[0]['use_global_blocked_services'])
    def test_global_change_during_permission(self):
        app.permit('iMac de Emma','youtube',20)
        app.save_global({'blocked_services':{'ids':['youtube','twitch'],'schedule':{'time_zone':'Local'}}})
        self.assertEqual(app.DEMO_CLIENTS[0]['blocked_services'],['twitch'])
        self.expire()
        self.assertEqual(app.effective(app.DEMO_CLIENTS[0],app.global_config())['blocked_services'],['youtube','twitch'])
    def test_client_edit_during_permission(self):
        app.permit('iMac de Emma','youtube',20)
        app.save_client('iMac de Emma',{'use_global_blocked_services':False,'blocked_services':['youtube','twitch'],'ignore_statistics':True})
        self.assertEqual(app.DEMO_CLIENTS[0]['blocked_services'],['twitch'])
        self.expire()
        self.assertFalse(app.DEMO_CLIENTS[0]['use_global_blocked_services'])
        self.assertEqual(app.DEMO_CLIENTS[0]['blocked_services'],['youtube','twitch'])
        self.assertTrue(app.DEMO_CLIENTS[0]['ignore_statistics'])
    def test_external_changes_preserved(self):
        app.permit('iMac de Emma','youtube',20)
        app.DEMO_CLIENTS[0]['ignore_statistics']=True
        app.DEMO_CLIENTS[0]['blocked_services']=['youtube','twitch']
        app.reconcile();self.expire()
        self.assertTrue(app.DEMO_CLIENTS[0]['ignore_statistics'])
        self.assertEqual(app.DEMO_CLIENTS[0]['blocked_services'],['youtube','twitch'])
    def test_remote_failure_retains_intent(self):
        original=app.api
        def failing(path,payload=None,*args,**kwargs):
            if path=='clients/update': raise OSError('offline')
            return original(path,payload,*args,**kwargs)
        app.api=failing
        try:
            with self.assertRaises(RuntimeError):app.permit('iMac de Emma','youtube',20)
            self.assertEqual(app.DB.execute('SELECT count(*) FROM leases').fetchone()[0],1)
        finally:app.api=original
        app.reconcile();self.assertEqual(app.DEMO_CLIENTS[0]['blocked_services'],['tiktok'])
        self.expire();self.assertTrue(app.DEMO_CLIENTS[0]['use_global_blocked_services'])
    def test_filtering_lease_preserves_other_global_settings(self):
        app.permit('iMac de Emma','@safesearch',20)
        self.assertFalse(app.DEMO_CLIENTS[0]['use_global_settings'])
        self.assertFalse(app.DEMO_CLIENTS[0]['safe_search']['enabled'])
        self.assertTrue(app.DEMO_CLIENTS[0]['parental_enabled'])
        app.save_global({'parental_enabled':False})
        self.assertFalse(app.DEMO_CLIENTS[0]['parental_enabled'])
        self.expire();self.assertTrue(app.DEMO_CLIENTS[0]['use_global_settings'])
    def test_two_inheritance_groups_independent(self):
        app.permit('iMac de Emma','youtube',20);app.permit('iMac de Emma','@parental',30)
        self.expire('youtube')
        self.assertTrue(app.DEMO_CLIENTS[0]['use_global_blocked_services'])
        self.assertFalse(app.DEMO_CLIENTS[0]['use_global_settings'])
        self.expire();self.assertTrue(app.DEMO_CLIENTS[0]['use_global_settings'])
    def test_dynamic_clients_and_config(self):
        app.save_client('',{'name':'Tablet','ids':['192.168.1.80'],'use_global_settings':True,'use_global_blocked_services':True},True)
        self.assertEqual(len(app.state()['clients']),3)
        app.save_client('Tablet',{'upstreams':['https://dns.example/dns-query'],'upstreams_cache_size':4096,'ignore_querylog':True})
        self.assertTrue(app.state()['base_clients']['Tablet']['ignore_querylog'])
    def test_server_password_not_exposed_and_switch_guard(self):
        app.save_server({'url':'http://example','username':'admin','password':'secret','demo':True})
        self.assertNotIn('password',app.public_server())
        app.permit('iMac de Emma','youtube',20)
        with self.assertRaises(ValueError):app.save_server({'demo':True})
    def test_global_put_and_preserved_interval(self):
        app.save_global({'safe_search':dict.fromkeys(app.SAFE_KEYS,False),'filtering_enabled':False})
        self.assertFalse(app.global_config()['safe_search']['enabled'])
        self.assertFalse(app.global_config()['filtering_enabled'])
    def test_validation(self):
        for value in (0,1441,True,'20'):
            with self.assertRaises(ValueError):app.permit('iMac de Emma','youtube',value)
        with self.assertRaises(ValueError):app.validate_schedule({'mon':{'start':100,'end':60000}})
        with self.assertRaises(ValueError):app.save_client('iMac de Emma',{'blocked_services':['fake']})
    def test_cidr_notification_identity(self):
        app.DEMO_CLIENTS[0]['ids']=['192.168.2.0/24']
        self.assertEqual(app.client_identity({'client':'192.168.2.45'},app.DEMO_CLIENTS),'iMac de Emma')

    def test_client_own_services_and_return_to_global(self):
        app.save_client('iMac de Martín',{'use_global_blocked_services':False,'blocked_services':['youtube'],'blocked_services_schedule':{'time_zone':'Local'}})
        state=app.state()
        self.assertEqual(state['effective']['iMac de Martín']['blocked_services'],['youtube'])
        self.assertTrue(state['base_clients']['iMac de Martín']['use_global_settings'])
        app.save_client('iMac de Martín',{'use_global_blocked_services':True})
        state=app.state()
        self.assertEqual(state['base_clients']['iMac de Martín']['blocked_services'],['youtube'])
        self.assertEqual(state['effective']['iMac de Martín']['blocked_services'],['youtube','tiktok'])

    def test_icon_persists_across_connection_and_rename(self):
        user={'role':'admin','id':1,'clients':[]}
        before=copy.deepcopy(app.DEMO_CLIENTS[0])
        with patch('auth.audit'): app.save_client_icon(user,before['name'],'tv')
        with sqlite3.connect(app.DATA/'state.db') as db:
            self.assertEqual(db.execute('SELECT icon FROM client_appearance').fetchone()[0],'tv')
        app.save_client(before['name'],{'name':'Nuevo nombre'})
        after=app.attach_appearance(copy.deepcopy(app.DEMO_CLIENTS[0]))
        self.assertEqual(after['ui_icon'],'tv')
        self.assertEqual(app.attach_appearance(copy.deepcopy(app.DEMO_CLIENTS[1]))['ui_icon'],None)
        with patch('auth.audit'): app.save_client_icon(user,'Nuevo nombre','auto')
        self.assertIsNone(app.attach_appearance(copy.deepcopy(app.DEMO_CLIENTS[0]))['ui_icon'])

    def test_icon_identity_ignores_identifier_order(self):
        self.assertEqual(app.appearance_identity({'name':'A','ids':['one','two']}),app.appearance_identity({'name':'B','ids':['two','one']}))

    def test_icon_roles_and_client_scope(self):
        client=app.DEMO_CLIENTS[0]['name']
        for role in ('solicitante','observador'):
            with self.assertRaises(app.auth.Forbidden): app.save_client_icon({'role':role,'clients':[client]},client,'tv')
        with self.assertRaises(app.auth.Forbidden): app.save_client_icon({'role':'responsable','clients':[]},client,'tv')
        with patch('auth.audit'): app.save_client_icon({'role':'responsable','clients':[client],'edit_policy':False},client,'tv')
        self.assertEqual(app.attach_appearance(copy.deepcopy(app.DEMO_CLIENTS[0]))['ui_icon'],'tv')
        with self.assertRaises(ValueError): app.save_client_icon({'role':'admin'},client,'../private')
        with self.assertRaises(ValueError): app.save_client_icon({'role':'admin'},'Missing','tv')

    def test_icon_does_not_change_filters_or_leases(self):
        app.permit('iMac de Emma','youtube',20)
        before=copy.deepcopy(app.DEMO_CLIENTS)
        leases=app.DB.execute('SELECT * FROM leases').fetchall()
        with patch('auth.audit'): app.save_client_icon({'role':'admin'},'iMac de Emma','laptop')
        self.assertEqual(before,app.DEMO_CLIENTS)
        self.assertEqual(leases,app.DB.execute('SELECT * FROM leases').fetchall())

    def test_console_icon_uses_separate_provider_identity(self):
        device={'key':'nintendo:ABC','name':'Switch'}
        with patch.object(app.NINTENDO,'devices',return_value={'devices':[device]}),patch('auth.audit'):
            app.save_client_icon({'role':'admin'},'nintendo:ABC','gamepad-2')
        result=app.attach_appearance(copy.deepcopy(device),'nintendo')
        self.assertEqual(result['ui_icon'],'gamepad-2')
        self.assertEqual(result['ui_auto_icon'],'gamepad-2')

    def test_restricted_user_receives_device_icon_without_settings(self):
        c=app.DEMO_CLIENTS[0];c['tags']=['device_tv']
        with patch('auth.requests_for',return_value=[]):
            result=app.scoped_state({'role':'solicitante','clients':[c['name']]})
        self.assertEqual(result['clients'][0]['ui_auto_icon'],'tv')
        self.assertNotIn('tags',result['clients'][0])

if __name__=='__main__':unittest.main()
