"""Signed OIDC responses, local-account linking, replay prevention and role preservation."""
import json, os, secrets, tempfile, time, unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt, auth, app, oidc


class OIDCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signer=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        cls.jwk=json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.signer.public_key()))|{'kid':'test-key','alg':'RS256','use':'sig'}

    def setUp(self):
        self.folder=Path(tempfile.mkdtemp());auth.init(self.folder)
        self.admin=auth.bootstrap('test','test','admin','secure-password-1234')
        self.child=auth.save_user(self.admin,{'username':'emma','password':'child-password-1234','role':'solicitante','clients':['Emma'],'avatar':'face-06'})
        self.other=auth.save_user(self.admin,{'username':'martin','password':'other-password-1234','role':'solicitante','clients':['Martin']})
        self.token,self.csrf,_=auth.login('emma','child-password-1234','test')
        self.local_admin,_,_=auth.login('admin','secure-password-1234','test')
        self.conn=oidc.Connector(self.folder)
        self.cfg={'enabled':True,'issuer':'https://auth.test/application/o/parental/','discovery_url':'https://auth.test/application/o/parental/.well-known/openid-configuration','public_url':'https://parental.test','client_id':'parental-client','client_secret':'test-confidential-secret','revision':'revision-1'}
        self.conn.path.write_text(json.dumps(self.cfg))
        self.meta={'issuer':self.cfg['issuer'],'authorization_endpoint':'https://auth.test/application/o/authorize/','token_endpoint':'https://auth.test/application/o/token/','jwks_uri':'https://auth.test/application/o/parental/jwks/','code_challenge_methods_supported':['S256'],'grant_types_supported':['authorization_code']}
        self.sub='immutable-subject';self.override={};self.sent=[]
        self.conn.http_json=self.http

    def claims(self,nonce):
        now=time.time()
        return {'iss':self.cfg['issuer'],'aud':self.cfg['client_id'],'sub':self.sub,'nonce':nonce,'exp':now+120,'iat':now,'preferred_username':'emma','email':'emma@example.test','groups':['admin']}|self.override

    def http(self,url,data=None):
        if url==self.cfg['discovery_url']:return self.meta
        if url==self.meta['jwks_uri']:return {'keys':[self.jwk]}
        if url==self.meta['token_endpoint']:
            self.sent.append(data)
            return {'id_token':jwt.encode(self.claims(self.nonce),self.signer,algorithm='RS256',headers={'kid':'test-key'})}
        raise AssertionError('Unexpected provider URL')

    def start(self,link=True,user=None,token=None,password=None,target='/'):
        user=user or self.child;token=token or self.token
        url,binding=self.conn.begin(target,user if link else None,token if link else '',password or 'child-password-1234',ip='test')
        query=parse_qs(urlsplit(url).query);self.nonce=query['nonce'][0]
        return query['state'][0],binding,query

    def link(self,user=None,token=None,password=None):
        user=user or self.child;token=token or self.token
        state,binding,q=self.start(user=user,token=token,password=password)
        result=self.conn.callback(state,'authorization-code',binding)
        pending=self.conn.status(user,token,binding)['pending']
        self.conn.confirm(user,pending['confirmation'],token,binding)
        return binding

    def test_link_requires_two_verified_accounts_and_confirmation_preserves_history(self):
        request=auth.request_access(self.child,{'client':'Emma','service':'youtube','minutes':20},lambda *a:None)
        state,binding,query=self.start()
        self.assertEqual(query['code_challenge_method'],['S256'])
        self.assertEqual(query['redirect_uri'],['https://parental.test'+oidc.CALLBACK])
        flow=auth.DB.execute('SELECT * FROM oidc_flows').fetchone()
        self.assertNotEqual(flow['state'],state);self.assertNotEqual(flow['binding'],binding)
        result=self.conn.callback(state,'code',binding)
        self.assertNotIn('token',result)
        self.assertFalse(self.conn.status(self.child)['linked'])
        pending=self.conn.status(self.child,self.token,binding)['pending']
        self.conn.confirm(self.child,pending['confirmation'],self.token,binding)
        self.assertTrue(self.conn.status(self.child)['linked'])
        self.assertEqual(auth.session(self.token)['avatar'],'face-06')
        self.assertEqual(auth.requests_for(self.child)[0]['id'],request)
        with self.assertRaises(oidc.OIDCError):self.conn.confirm(self.child,pending['confirmation'],self.token,binding)

    def test_sso_uses_same_local_user_and_ignores_external_admin_group(self):
        self.link();state,binding,_=self.start(link=False,target='/?view=requests#request=14')
        result=self.conn.callback(state,'code',binding)
        self.assertEqual(result['target'],'/?view=requests#request=14')
        user=auth.session(result['token'])
        self.assertEqual((user['id'],user['role'],user['clients']),(self.child['id'],'solicitante',['Emma']))
        with self.assertRaises(auth.Forbidden):auth.grant(user,'Emma',10)
        self.assertEqual(auth.DB.execute('SELECT count(*) FROM users').fetchone()[0],3)
        self.assertNotIn('code_verifier',result)
        self.assertEqual(self.sent[-1]['client_secret'],self.cfg['client_secret'])

    def test_name_or_email_match_never_links_automatically(self):
        state,binding,_=self.start(link=False)
        with self.assertRaisesRegex(oidc.OIDCError,'no está vinculada'):self.conn.callback(state,'code',binding)
        self.assertEqual(auth.DB.execute('SELECT count(*) FROM external_identities').fetchone()[0],0)
        self.assertEqual(auth.DB.execute('SELECT count(*) FROM users').fetchone()[0],3)

    def test_first_login_links_by_verified_email_only(self):
        auth.save_user(self.admin,{'id':self.child['id'],'email':'Emma@Example.test'})
        state,binding,query=self.start(link=False)
        self.assertIn('email',query['scope'][0].split())
        with self.assertRaisesRegex(oidc.OIDCError,'no está vinculada'):self.conn.callback(state,'code',binding)  # email_verified missing
        self.override={'email_verified':'true'}  # Only a JSON true counts.
        state,binding,_=self.start(link=False)
        with self.assertRaises(oidc.OIDCError):self.conn.callback(state,'code',binding)
        self.override={'email_verified':True}
        state,binding,_=self.start(link=False);result=self.conn.callback(state,'code',binding)
        self.assertEqual(result['user']['id'],self.child['id'])
        self.assertEqual(auth.DB.execute('SELECT user_id FROM external_identities WHERE subject=?',(self.sub,)).fetchone()[0],self.child['id'])
        self.assertTrue(auth.DB.execute("SELECT 1 FROM audit WHERE action='authentik_auto_linked'").fetchone())

    def test_trusted_authentik_email_links_unverified_but_never_by_name(self):
        auth.save_user(self.admin,{'id':self.child['id'],'email':'emma@example.test'})
        self.conn.path.write_text(json.dumps(self.cfg|{'trust_email':True}))
        self.override={'preferred_username':'martin'}  # Username is ignored; the e-mail decides.
        state,binding,_=self.start(link=False);result=self.conn.callback(state,'code',binding)
        self.assertEqual(result['user']['username'],'emma')
        self.override={'email':'nobody@example.test','preferred_username':'emma'};self.sub='another-subject'
        state,binding,_=self.start(link=False)
        with self.assertRaises(oidc.OIDCError):self.conn.callback(state,'code',binding)

    def test_email_auto_link_skips_disabled_or_already_linked_accounts(self):
        auth.save_user(self.admin,{'id':self.child['id'],'email':'emma@example.test'})
        self.conn.path.write_text(json.dumps(self.cfg|{'trust_email':True}))
        self.link()  # Emma already linked to immutable-subject.
        self.sub='second-identity';state,binding,_=self.start(link=False)
        with self.assertRaises(oidc.OIDCError):self.conn.callback(state,'code',binding)
        auth.save_user(self.admin,{'id':self.other['id'],'email':'martin@example.test','active':False})
        self.override={'email':'martin@example.test'};self.sub='third-identity';state,binding,_=self.start(link=False)
        with self.assertRaises(oidc.OIDCError):self.conn.callback(state,'code',binding)
        self.assertEqual(auth.DB.execute('SELECT count(*) FROM external_identities').fetchone()[0],1)

    def test_user_email_is_validated_and_unique(self):
        auth.save_user(self.admin,{'id':self.child['id'],'email':'emma@example.test'})
        with self.assertRaisesRegex(ValueError,'otra cuenta'):auth.save_user(self.admin,{'id':self.other['id'],'email':'EMMA@example.test'})
        with self.assertRaisesRegex(ValueError,'Correo'):auth.save_user(self.admin,{'id':self.other['id'],'email':'no-es-correo'})
        self.assertEqual(auth.save_user(self.admin,{'id':self.other['id'],'email':''})['email'],'')

    def test_replay_other_browser_and_expiry(self):
        state,binding,_=self.start(link=False)
        with self.assertRaises(oidc.OIDCError):self.conn.callback(state,'code','stolen-binding')
        self.assertFalse(self.sent)
        with self.assertRaises(oidc.OIDCError):self.conn.callback(state,'code',binding)
        self.assertEqual(len(self.sent),1)
        with self.assertRaises(oidc.OIDCError):self.conn.callback(state,'code',binding)
        self.assertEqual(len(self.sent),1)
        state,binding,_=self.start(link=False)
        auth.DB.execute('UPDATE oidc_flows SET expires=0');auth.DB.commit()
        with self.assertRaises(oidc.OIDCError):self.conn.callback(state,'code',binding)

    def test_duplicate_external_identity_cannot_join_two_users(self):
        self.link()
        token,_,_=auth.login('martin','other-password-1234','test')
        state,binding,_=self.start(user=self.other,token=token,password='other-password-1234')
        self.conn.callback(state,'code',binding)
        pending=self.conn.status(self.other,token,binding)['pending']
        with self.assertRaisesRegex(oidc.OIDCError,'otra cuenta'):self.conn.confirm(self.other,pending['confirmation'],token,binding)
        self.assertFalse(self.conn.status(self.other)['linked'])

    def test_wrong_local_password_and_logged_out_session_block_link(self):
        with self.assertRaises(auth.Forbidden):self.start(password='wrong')
        state,binding,_=self.start();auth.logout(self.token)
        with self.assertRaises(auth.Forbidden):self.conn.callback(state,'code',binding)
        self.assertFalse(self.sent)

    def test_local_session_revoked_between_callback_and_confirmation(self):
        state,binding,_=self.start();self.conn.callback(state,'code',binding)
        pending=self.conn.status(self.child,self.token,binding)['pending'];auth.logout(self.token)
        with self.assertRaises(auth.Forbidden):self.conn.confirm(self.child,pending['confirmation'],self.token,binding)

    def test_token_validation_rejects_bad_claims(self):
        for patch_claim in ({'iss':'https://other.test/'},{'aud':'other'},{'nonce':'wrong'},{'exp':time.time()-60},{'iat':time.time()+60},{'azp':'other'},{'aud':['parental-client','other']},{'sub':''}):
            with self.subTest(claim=patch_claim):
                token=jwt.encode(self.claims('nonce')|patch_claim,self.signer,algorithm='RS256',headers={'kid':'test-key'})
                with self.assertRaises(oidc.OIDCError):self.conn.verify_token(token,self.cfg,self.meta,'nonce')
        for missing in ('exp','iat','iss','aud','sub','nonce'):
            claims=self.claims('nonce');claims.pop(missing)
            token=jwt.encode(claims,self.signer,algorithm='RS256',headers={'kid':'test-key'})
            with self.assertRaises(oidc.OIDCError):self.conn.verify_token(token,self.cfg,self.meta,'nonce')

    def test_wrong_signature_algorithm_and_ambiguous_key(self):
        signer=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        token=jwt.encode(self.claims('nonce'),signer,algorithm='RS256',headers={'kid':'test-key'})
        with self.assertRaises(oidc.OIDCError):self.conn.verify_token(token,self.cfg,self.meta,'nonce')
        token=jwt.encode(self.claims('nonce'),'not-a-client-secret-but-long-enough',algorithm='HS256',headers={'kid':'test-key'})
        with self.assertRaises(oidc.OIDCError):self.conn.verify_token(token,self.cfg,self.meta,'nonce')

    def test_cancel_does_not_link(self):
        state,binding,_=self.start();self.conn.callback(state,'code',binding)
        pending=self.conn.status(self.child,self.token,binding)['pending'];self.conn.confirm(self.child,pending['confirmation'],self.token,binding,cancel=True)
        self.assertFalse(self.conn.status(self.child)['linked'])

    def test_disabled_users_cannot_use_sso(self):
        self.link();auth.save_user(self.admin,{'id':self.child['id'],'active':False})
        state,binding,_=self.start(link=False)
        with self.assertRaises(oidc.OIDCError):self.conn.callback(state,'code',binding)

    def test_subject_is_stable_when_username_changes(self):
        self.link();self.override={'preferred_username':'new-authentik-name'}
        state,binding,_=self.start(link=False);result=self.conn.callback(state,'code',binding)
        self.assertEqual(result['user']['username'],'emma')

    def test_unlink_revokes_sso_sessions_only_and_requires_password_scope(self):
        self.link();state,binding,_=self.start(link=False);sso=self.conn.callback(state,'code',binding)['token']
        with self.assertRaises(auth.Forbidden):self.conn.unlink(self.other,{'user_id':self.child['id'],'password':'other-password-1234'},'test')
        with self.assertRaises(auth.Forbidden):self.conn.unlink(self.child,{'password':'wrong'},'test')
        self.conn.unlink(self.child,{'password':'child-password-1234'},'test')
        self.assertIsNone(auth.session(sso));self.assertIsNotNone(auth.session(self.token))

    def test_config_secret_private_and_change_revokes_sso_pending_flows(self):
        self.link();state,binding,_=self.start(link=False);sso=self.conn.callback(state,'code',binding)['token']
        self.start(link=False)
        with self.assertRaises(auth.Forbidden):self.conn.save(self.child,{'password':'child-password-1234'},'test')
        cfg=self.conn.save(self.admin,{'enabled':False,'password':'secure-password-1234'},'test')
        self.assertNotIn('client_secret',cfg);self.assertTrue(cfg['secret_set'])
        self.assertEqual(self.conn.path.stat().st_mode&0o777,0o600)
        self.assertIsNone(auth.session(sso));self.assertIsNotNone(auth.session(self.local_admin))
        self.assertEqual(auth.DB.execute('SELECT count(*) FROM oidc_flows').fetchone()[0],0)

    def test_metadata_issuer_endpoint_pkce_and_signing_diagnostics(self):
        self.assertTrue(self.conn.test(self.admin)['ok'])
        for values in ({'issuer':'https://wrong.test/'},{'token_endpoint':'https://evil.test/token'},{'code_challenge_methods_supported':['plain']}):
            original=self.meta.copy();self.meta.update(values)
            with self.assertRaises(oidc.OIDCError):self.conn.metadata(self.cfg,force=True)
            self.meta=original

    def test_urls_and_safe_notification_destinations(self):
        for url in ('http://auth.test/','https://user:pass@auth.test/','https://auth.test/?token=secret','https://auth.test/#x'):
            with self.assertRaises(oidc.OIDCError):oidc.validated_url(url)
        for url in ('https://evil.test/','//evil.test/','/\\evil.test/','/?view=admin','http://['):
            self.assertNotIn('evil',oidc.destination(url));self.assertNotIn('admin',oidc.destination(url))
        self.assertEqual(oidc.destination('/?view=clients#client=Emma&service=youtube'),'/?view=clients#client=Emma&service=youtube')

    def test_http_role_and_csrf_gates_for_provider_configuration(self):
        handler=object.__new__(app.Handler);handler.path='/api/authentik/config';handler.headers={'Cookie':'session='+self.token,'X-CSRF-Token':self.csrf};handler.client_address=('test',0);handler.body=lambda:{'enabled':True,'password':'child-password-1234'};handler.respond=Mock()
        with patch.object(app,'AUTHENTIK',self.conn):handler.do_POST()
        self.assertEqual(handler.respond.call_args.args[0],403)
        handler.path='/api/me/authentik/unlink';handler.headers={'Cookie':'session='+self.token}
        with patch.object(app,'AUTHENTIK',self.conn):handler.do_POST()
        self.assertEqual(handler.respond.call_args.args[0],403)


if __name__=='__main__':unittest.main()
