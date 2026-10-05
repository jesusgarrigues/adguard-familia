"""AdGuard contract regression and recipient preferences, independent of the UI."""
import copy, json, tempfile, time, unittest
from datetime import datetime, timezone
from unittest.mock import patch
import app, auth, blocked_alerts

class BlockedQueriesTest(unittest.TestCase):
    def setUp(self):
        app.demo_reset()
        for table in ('events','seen','leases','baselines'): app.DB.execute('DELETE FROM '+table)
        app.DB.commit()
        app.DEMO_CLIENTS[0].update(name='Televisiones',ids=['192.168.212.0/24'])
        self.now=time.time()
    def query(self,reason='FilteredBlockedService',service='youtube',seconds=0,**extra):
        return dict(time=datetime.fromtimestamp(self.now+seconds,timezone.utc).isoformat(),client='192.168.212.20',reason=reason,service_name=service,question={'name':'www.youtube.com'},**extra)
    def poll(self,queries):
        original=app.api
        with patch.object(app,'api',side_effect=lambda path,*a,**kw: {'data':queries} if path.startswith('querylog') else original(path,*a,**kw)):
            app.poll()
        return app.state()['events']
    def test_official_service_reason_and_cidr(self):
        events=self.poll([self.query()])
        self.assertEqual([(e['client'],e['service']) for e in events],[('Televisiones','youtube')])
        self.assertAlmostEqual(events[0]['time'],self.now,places=4)
    def test_safe_search_and_dns_are_distinct(self):
        events=self.poll([self.query('FilteredSafeSearch'),self.query('FilteredBlackList',seconds=-1)])
        self.assertEqual({e['service'] for e in events},{'@safesearch','@filtering'})
    def test_known_auto_name_does_not_hide_registered_cidr(self):
        events=self.poll([self.query(client_info={'name':'tv-bedroom.local'})])
        self.assertEqual(events[0]['client'],'Televisiones')
    def test_most_specific_client_subnet(self):
        app.DEMO_CLIENTS.insert(0,dict(app.DEMO_CLIENTS[1],name='Red completa',ids=['192.168.0.0/16']))
        self.assertEqual(self.poll([self.query()])[0]['client'],'Televisiones')
    def test_client_id_and_ipv6(self):
        app.DEMO_CLIENTS[0]['ids']=['tv-bedroom','2001:db8:12::/64']
        q=self.query(client_id='tv-bedroom');q['client']='10.0.0.1'
        self.assertEqual(app.client_identity(q,app.DEMO_CLIENTS),'Televisiones')
        self.assertEqual(app.client_identity({'client':'2001:db8:12::2'},app.DEMO_CLIENTS),'Televisiones')
    def test_duplicate_burst_and_legacy_reason(self):
        queries=[self.query(),self.query('BlockedService',seconds=-10)]
        self.assertEqual(len(self.poll(queries)),1)
        self.assertEqual(len(self.poll(queries)),1)
    def test_unknown_service_and_invalid_time_have_diagnostic(self):
        invalid=self.query();invalid['time']='bad'
        self.assertEqual(self.poll([self.query(service='unknown'),invalid]),[])
        self.assertEqual(app.LAST_POLL['unknown'],2)
    def test_full_window_and_excluded_clients_are_visible(self):
        app.DEMO_CLIENTS[0]['ignore_querylog']=True
        self.poll([self.query('NotFilteredNotFound')]*500)
        self.assertTrue(app.LAST_POLL['window_full'])
        self.assertEqual(app.LAST_POLL['excluded_clients'],['Televisiones'])
    def test_stale_event_cannot_replace_a_current_lease(self):
        app.permit('Televisiones','youtube',10,require_blocked=True)
        before=app.DB.execute('SELECT expires FROM leases').fetchone()[0]
        with self.assertRaisesRegex(ValueError,'ya no está activa'):
            app.permit('Televisiones','youtube',60,require_blocked=True)
        self.assertEqual(app.DB.execute('SELECT expires FROM leases').fetchone()[0],before)
    def test_scope_feed_does_not_leak_other_clients(self):
        app.event('Televisiones','youtube');app.event('iMac de Martín','youtube')
        user={'id':101,'role':'responsable','clients':['Televisiones'],'edit_policy':False}
        result=app.scoped_state(user)
        self.assertEqual({e['client'] for e in result['notification_events']},{'Televisiones'})

class PreferencesTest(unittest.TestCase):
    def setUp(self):
        self.old_db=auth.DB
        auth.init(tempfile.mkdtemp())
        self.user=auth.bootstrap('setup','setup','adult','adult-password-1234')
        self.parent=dict(self.user,id=2,role='responsable',clients=['Televisiones'])
        self.now=time.time()
        self.catalog={'youtube','netflix','tiktok'};self.allowed={'Televisiones','Ordenador'}
    def tearDown(self):
        auth.DB.close();auth.DB=self.old_db
    def event(self,service='youtube',client='Televisiones',seconds=0,id=1):
        return {'id':id,'kind':'blocked','service':service,'client':client,'time':self.now+seconds}
    def feed(self,events,preferences=None,user=None,updated=0):
        return blocked_alerts.eligible(user or self.user,events,{'preferences':preferences or blocked_alerts.defaults(),'updated':updated},self.now)
    def test_defaults_services_only_and_no_historical_replay(self):
        events=[self.event(),self.event('@filtering',id=2),self.event(seconds=-400,id=3)]
        self.assertEqual([e['id'] for e in self.feed(events)],[1])
    def test_selection_override_and_optional_protections(self):
        prefs=blocked_alerts.defaults();prefs.update(mode='selected',services=['netflix'])
        prefs['clients']['Televisiones']={'mode':'selected','services':['youtube'],'protections':['@safesearch']}
        events=[self.event(),self.event('netflix',id=2),self.event('@safesearch',id=3),self.event('netflix','Ordenador',id=4)]
        self.assertEqual([e['id'] for e in self.feed(events,prefs)],[1,3,4])
    def test_none_services_can_keep_selected_protection(self):
        prefs=blocked_alerts.defaults();prefs.update(mode='none',protections=['@filtering'])
        self.assertEqual([e['id'] for e in self.feed([self.event(),self.event('@filtering',id=2)],prefs)],[2])
    def test_roles_and_scope(self):
        for role in ('solicitante','observador'):
            self.assertEqual(self.feed([self.event()],user=dict(self.user,role=role)),[])
        self.assertEqual(self.feed([self.event(client='Ordenador')],user=self.parent),[])
    def test_cooldown_is_per_client_and_service(self):
        prefs=blocked_alerts.defaults();prefs['cooldown_minutes']=10
        events=[self.event(seconds=-400,id=1),self.event(id=2),self.event('netflix',id=3),self.event(client='Ordenador',id=4)]
        self.assertEqual([e['id'] for e in self.feed(events,prefs)],[3,4])
    def test_saved_preferences_survive_reopen_and_do_not_change_policy(self):
        before=copy.deepcopy(app.DEMO_CLIENTS)
        config=blocked_alerts.defaults();config.update(mode='selected',services=['youtube'])
        blocked_alerts.save(self.user,config,self.catalog,self.allowed)
        path=auth.DB.execute('PRAGMA database_list').fetchone()[2];auth.DB.close();auth.init(__import__('pathlib').Path(path).parent)
        self.assertEqual(blocked_alerts.preferences(self.user)['preferences']['services'],['youtube'])
        self.assertEqual(app.DEMO_CLIENTS,before)
    def test_changes_do_not_notify_older_events(self):
        self.assertEqual(self.feed([self.event()],updated=self.now+1),[])
    def test_invalid_unknown_and_out_of_scope(self):
        variants=[dict(blocked_alerts.defaults(),services=['unknown']),dict(blocked_alerts.defaults(),cooldown_minutes=True),dict(blocked_alerts.defaults(),cooldown_minutes=0),dict(blocked_alerts.defaults(),protections=['youtube']),dict(blocked_alerts.defaults(),role='admin')]
        for config in variants:
            with self.assertRaises(ValueError):blocked_alerts.save(self.user,config,self.catalog,self.allowed)
        config=blocked_alerts.defaults();config['clients']={'Ordenador':{'mode':'all','services':[],'protections':[]}}
        with self.assertRaises(auth.Forbidden):blocked_alerts.save(self.parent,config,self.catalog,{'Televisiones'})
        with self.assertRaises(auth.Forbidden):blocked_alerts.save(dict(self.user,role='solicitante'),blocked_alerts.defaults(),self.catalog,self.allowed)
    def test_other_recipients_are_independent(self):
        config=blocked_alerts.defaults();config['mode']='none'
        blocked_alerts.save(self.user,config,self.catalog,self.allowed)
        self.assertEqual(blocked_alerts.preferences(self.parent)['preferences']['mode'],'all')
    def test_assignments_hide_existing_preferences(self):
        config=blocked_alerts.defaults();config['clients']={'Ordenador':{'mode':'selected','services':['youtube'],'protections':[]}}
        blocked_alerts.save(self.user,config,self.catalog,self.allowed)
        self.assertEqual(blocked_alerts.preferences(self.user,{'Televisiones'})['preferences']['clients'],{})
        blocked_alerts.save(self.user,blocked_alerts.defaults(),self.catalog,{'Televisiones'})
        self.assertIn('Ordenador',blocked_alerts.preferences(self.user,self.allowed)['preferences']['clients'])

if __name__=='__main__':unittest.main()
