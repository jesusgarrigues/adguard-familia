import copy, importlib, os, tempfile, unittest
os.environ['DATA_DIR']=tempfile.mkdtemp()
os.environ['DEMO']='true'
import app

class PermissionsTest(unittest.TestCase):
    def setUp(self):
        for table in ('leases','baselines','events','seen','settings'): app.DB.execute('DELETE FROM '+table)
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

if __name__=='__main__':unittest.main()
