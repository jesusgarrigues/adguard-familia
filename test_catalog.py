import hashlib,json,tempfile,unittest
from pathlib import Path
import app,auth

class CatalogTests(unittest.TestCase):
    def test_catalog_assets_and_frontend_backend_match(self):
        data=json.loads((app.ROOT/'assets/appearance-catalog.json').read_text())
        js=(app.ROOT/'assets/appearance-catalog.js').read_text()
        self.assertEqual(json.loads(js.split('ParentalCatalog=',1)[1].rstrip(';\n')),data)
        self.assertEqual(len(data['devices']),91);self.assertEqual(len(data['avatars']),80)
        self.assertEqual(set(app.DEVICE_ICONS),{x['id'] for x in data['devices']})
        self.assertEqual(set(auth.AVATARS)-{''},{x['id'] for x in data['avatars']})
        for kind,items in [('icons',data['devices']),('avatars',data['avatars'])]:
            for item in items:
                path='/assets/'+kind+'/'+item['id']+'.svg'
                self.assertIn(path,app.STATIC_ASSETS)
                content=(app.ROOT/path.lstrip('/')).read_text()
                self.assertIn('<svg',content);self.assertNotIn('<script',content)
        avatars=[(app.ROOT/'assets/avatars'/f'{x["id"]}.svg').read_bytes() for x in data['avatars']]
        self.assertEqual(len(set(avatars)),80)

    def test_specific_model_detection_and_preserved_original_keys(self):
        original={'monitor','laptop','smartphone','tablet','gamepad-2','tv','router','printer','speaker','headphones','watch','server'}
        self.assertTrue(original<=set(app.DEVICE_ICONS))
        for name,key in [('iMac de Emma','imac'),('iPhone de Martín','iphone'),('iPad Pro','ipad-pro'),('Fire TV 4K Max','fire-tv-4k-max'),('Echo Show 10','echo-show-10'),('Home Assistant Green','ha-green'),('Proxmox Backup Server','proxmox-backup')]:
            self.assertEqual(app.automatic_icon({'name':name,'tags':['device_pc']}),key)

    def test_new_avatar_preserves_role_and_session(self):
        auth.init(tempfile.mkdtemp());admin=auth.bootstrap('test','test','admin','secure-password-1234')
        user=auth.save_user(admin,{'username':'emma','password':'child-password-1234','role':'solicitante','clients':['Emma']})
        token,_,_=auth.login('emma','child-password-1234','test')
        saved=auth.save_avatar(user,{'avatar':'animal-24'})
        self.assertEqual((saved['id'],saved['role'],saved['clients']),(user['id'],'solicitante',['Emma']))
        self.assertEqual(auth.session(token)['avatar'],'animal-24')
