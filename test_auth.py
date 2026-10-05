import io, tempfile, unittest
from unittest.mock import Mock, patch
import auth, app

class RoleTests(unittest.TestCase):
    def setUp(self):
        auth.init(tempfile.mkdtemp())
        self.admin=auth.bootstrap('bootstrap-secret','bootstrap-secret','admin','secure-password-1234')
        self.child=auth.save_user(self.admin,{'username':'emma','password':'child-password-1234','role':'solicitante','clients':['Emma']})
        self.manager=auth.save_user(self.admin,{'username':'parent','password':'parent-password-1234','role':'responsable','clients':['Emma'],'max_minutes':60})
        self.observer=auth.save_user(self.admin,{'username':'observer','password':'observer-password-1234','role':'observador','clients':['Emma']})
    def request(self):return auth.request_access(self.child,{'client':'Emma','service':'youtube','minutes':20,'reason':'Vídeo de clase'},lambda c,s:None)
    def test_request_never_grants_permission(self):
        rid=self.request()
        self.assertEqual(auth.requests_for(self.child)[0]['status'],'pending')
        self.assertGreater(rid,0)
        with self.assertRaises(auth.Forbidden):auth.grant(self.child,'Emma',20)
        with self.assertRaises(auth.Forbidden):auth.review(self.child,{'id':rid,'decision':'approve'},Mock())
    def test_scope_and_observer_cannot_mutate(self):
        with self.assertRaises(auth.Forbidden):auth.grant(self.manager,'Martin',20)
        with self.assertRaises(auth.Forbidden):auth.request_access(self.child,{'client':'Martin','service':'youtube','minutes':20},Mock())
        with self.assertRaises(auth.Forbidden):auth.grant(self.observer,'Emma',20)
        with self.assertRaises(auth.Forbidden):auth.save_user(self.manager,{'username':'evil','role':'admin'})
    def test_approval_required_and_adjusted_duration(self):
        rid=self.request();grant=Mock()
        auth.review(self.manager,{'id':rid,'decision':'approve','minutes':15},grant)
        grant.assert_called_once_with('Emma','youtube',15)
        self.assertEqual(auth.requests_for(self.child)[0]['approved_minutes'],15)
        with self.assertRaises(ValueError):auth.review(self.manager,{'id':rid,'decision':'approve'},grant)
    def test_rejection_and_withdrawal_no_grant(self):
        rid=self.request();grant=Mock();auth.review(self.manager,{'id':rid,'decision':'reject'},grant);grant.assert_not_called()
        rid=self.request();auth.withdraw(self.child,rid)
        self.assertEqual(auth.requests_for(self.child)[0]['status'],'withdrawn')
    def test_duration_and_edit_limits(self):
        with self.assertRaises(ValueError):auth.grant(self.manager,'Emma',61)
        with self.assertRaises(auth.Forbidden):auth.grant(self.manager,'Emma',edit=True)
        manager=auth.save_user(self.admin,{'id':self.manager['id'],'edit_policy':True})
        auth.grant(manager,'Emma',edit=True)
    def test_password_hash_sessions_revocation(self):
        row=auth.DB.execute('SELECT password FROM users WHERE id=?',(self.child['id'],)).fetchone()
        self.assertNotIn('child-password',row['password'])
        token,csrf,user=auth.login('emma','child-password-1234','127.0.0.1')
        self.assertEqual(auth.session(token)['csrf'],csrf)
        auth.save_user(self.admin,{'id':user['id'],'active':False})
        self.assertIsNone(auth.session(token))
    def test_last_admin_and_bootstrap_once(self):
        with self.assertRaises(ValueError):auth.save_user(self.admin,{'id':self.admin['id'],'active':False})
        with self.assertRaises(auth.Forbidden):auth.bootstrap('bootstrap-secret','bootstrap-secret','next','secure-password-1234')
    def test_role_enforced_by_http_handler(self):
        token,csrf,_=auth.login('emma','child-password-1234','127.0.0.1')
        handler=object.__new__(app.Handler);handler.headers={'Cookie':'session='+token,'X-CSRF-Token':csrf};handler.path='/api/permit';handler.body=lambda:{'client':'Emma','service':'youtube','minutes':20};handler.respond=Mock()
        with patch.object(app,'permit') as grant:
            handler.do_POST();grant.assert_not_called()
        self.assertEqual(handler.respond.call_args.args[0],403)
    def test_csrf_and_legacy_key_do_not_grant_access(self):
        token,csrf,_=auth.login('admin','secure-password-1234','127.0.0.1')
        handler=object.__new__(app.Handler);handler.headers={'Cookie':'session='+token};handler.path='/api/permit';handler.body=lambda:{'client':'Emma','service':'youtube','minutes':20};handler.respond=Mock()
        handler.do_POST();self.assertEqual(handler.respond.call_args.args[0],403)
        handler.headers={'Authorization':'Bearer '+app.TOKEN};handler.do_POST();self.assertEqual(handler.respond.call_args.args[0],401)
    def test_scoped_state_does_not_expose_dns_history_or_server(self):
        fake={'clients':[{'name':'Emma','ids':['1']},{'name':'Martin','ids':['2']}],'base_clients':{'Emma':{'name':'Emma','upstreams':['private-dns']},'Martin':{}},'effective':{'Emma':{},'Martin':{}},'base_effective':{'Emma':{},'Martin':{}},'leases':[],'events':[{'client':'Emma','domain':'private.com'}],'server':{'url':'private-server'},'auto_clients':[],'global_config':{'protection_enabled':True},'error':'internal'}
        with patch.object(app,'state',return_value=fake):result=app.scoped_state(self.child)
        self.assertEqual(result['events'],[]);self.assertEqual(result['server'],{});self.assertEqual(len(result['clients']),1)
        self.assertNotIn('upstreams',result['base_clients']['Emma'])
    def test_failed_authentication_throttled(self):
        for _ in range(5):
            with self.assertRaises(auth.Forbidden):auth.login('emma','incorrect','ip')
        with self.assertRaisesRegex(auth.Forbidden,'15 minutos'):auth.login('emma','child-password-1234','ip')

    def test_avatar_persists_without_revoking_session_or_changing_permissions(self):
        token,csrf,user=auth.login('emma','child-password-1234','127.0.0.1')
        changed=auth.save_avatar(user,{'avatar':'face-03'})
        self.assertEqual((changed['avatar'],changed['role'],changed['clients']),('face-03','solicitante',['Emma']))
        self.assertEqual(auth.session(token)['csrf'],csrf)
        folder=auth.DB.execute('PRAGMA database_list').fetchone()[2]
        auth.DB.close();auth.init(__import__('pathlib').Path(folder).parent)
        self.assertEqual(auth.session(token)['avatar'],'face-03')
    def test_avatar_cannot_change_other_users_or_privileges(self):
        with self.assertRaises(auth.Forbidden):auth.save_avatar(self.manager,{'user_id':self.child['id'],'avatar':'face-04'})
        with self.assertRaises(ValueError):auth.save_avatar(self.child,{'avatar':'face-04','role':'admin'})
        for invalid in ('../../../secret','https://example.com/a.svg','face-99',None,[],1):
            with self.assertRaises(ValueError):auth.save_avatar(self.child,{'avatar':invalid})
        with self.assertRaises(ValueError):auth.save_avatar(self.admin,{'user_id':False,'avatar':'face-04'})
    def test_admin_cosmetic_edit_keeps_sessions(self):
        token,_,_=auth.login('emma','child-password-1234','127.0.0.1')
        changed=auth.save_user(self.admin,{'id':self.child['id'],'avatar':'face-05'})
        self.assertEqual(changed['avatar'],'face-05');self.assertIsNotNone(auth.session(token))
        auth.save_avatar(self.admin,{'user_id':self.child['id'],'avatar':''})
        self.assertEqual(auth.session(token)['avatar'],'')
    def test_requests_use_current_avatar(self):
        self.request();auth.save_avatar(self.child,{'avatar':'face-07'})
        self.assertEqual(auth.requests_for(self.manager)[0]['avatar'],'face-07')
    def test_migration_keeps_old_users_and_sessions(self):
        token,csrf,_=auth.login('emma','child-password-1234','127.0.0.1')
        auth.DB.execute('ALTER TABLE users DROP COLUMN avatar');auth.DB.commit()
        folder=auth.DB.execute('PRAGMA database_list').fetchone()[2]
        auth.DB.close();auth.init(__import__('pathlib').Path(folder).parent)
        user=auth.session(token)
        self.assertEqual((user['avatar'],user['role'],user['clients'],user['csrf']),('','solicitante',['Emma'],csrf))
        auth.init(__import__('pathlib').Path(folder).parent)
        self.assertEqual(auth.session(token)['avatar'],'')
    def test_avatar_http_csrf_and_self_scope(self):
        token,csrf,_=auth.login('emma','child-password-1234','127.0.0.1')
        h=object.__new__(app.Handler);h.headers={'Cookie':'session='+token};h.path='/api/me/avatar';h.respond=Mock();h.body=lambda:{'avatar':'face-02'}
        h.do_POST();self.assertEqual(h.respond.call_args.args[0],403)
        h.headers['X-CSRF-Token']=csrf;h.do_POST();self.assertEqual(h.respond.call_args.args[0],200)
        h.body=lambda:{'avatar':'face-02','user_id':self.admin['id']};h.do_POST();self.assertEqual(h.respond.call_args.args[0],400)
        h.path='/api/users/avatar';h.do_POST();self.assertEqual(h.respond.call_args.args[0],403)

if __name__=='__main__':unittest.main()
