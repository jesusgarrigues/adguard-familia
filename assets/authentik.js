(() => {
  'use strict';
  const make=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;if(cls)node.className=cls;return node;};
  const field=(root,label,value='',type='text')=>{const wrap=make('label','','field'),input=make('input');input.type=type;input.value=value;input.autocomplete=type==='password'?'current-password':'off';wrap.append(make('span',label),input);root.append(wrap);return input;};
  const button=(label,fn,cls='')=>{const node=make('button',label,cls);node.type='button';node.onclick=fn;return node;};
  const feedback=()=>{const node=make('p','','authentik-feedback');node.setAttribute('role','status');return node;};

  function login(root){
    const b=button('Continuar con Authentik',()=>{b.disabled=true;location.assign('/api/auth/oidc/start?target='+encodeURIComponent(location.pathname+location.search+location.hash));},'authentik-login');root.append(b);
  }

  async function profile(root,account,options){
    const panel=make('section','','identity-account');panel.append(make('h4','Acceso con Authentik'));root.append(panel);
    const status=feedback();panel.append(status);status.textContent='Comprobando vinculación…';
    try{
      const data=await options.request('me/authentik');if(!panel.isConnected)return;
      panel.replaceChildren(make('h4','Acceso con Authentik'));
      panel.append(make('p',data.linked?'Vinculado con '+data.identity.label: data.enabled?'Puedes utilizar Authentik con esta misma cuenta y sus permisos.':'El administrador todavía no ha habilitado Authentik.'));
      if(data.pending){
        const confirm=make('div','','authentik-confirmation');confirm.append(make('strong','Confirmar vinculación'),make('p','Cuenta Parental: '+account.username),make('p','Identidad Authentik: '+data.pending.label));
          const actions=make('div','','identity-actions');
        for(const [label,path]of [['Vincular estas cuentas','confirm'],['Cancelar','cancel']])actions.append(button(label,async()=>{for(const b of actions.querySelectorAll('button'))b.disabled=true;try{await options.request('me/authentik/'+path,{confirmation:data.pending.confirmation});if(!panel.isConnected)return;status.textContent=path==='confirm'?'Cuentas vinculadas. Ya puedes entrar con Authentik.':'Vinculación cancelada.';await profile(root,account,options);panel.remove();}catch(error){status.textContent=error.message;for(const b of actions.querySelectorAll('button'))b.disabled=false;}},path==='confirm'?'primary':''));
        confirm.append(actions);panel.append(confirm,status);confirm.scrollIntoView({block:'nearest'});return;
      }
      if(!data.enabled&&!data.linked){panel.append(status);status.textContent='';return;}
      const password=field(panel,'Confirma tu contraseña local de Parental','','password');
      const action=button(data.linked?'Desvincular Authentik':'Vincular Authentik',async()=>{
        if(!password.value){status.textContent='Introduce tu contraseña local para continuar.';password.focus();return;}
        if(data.linked&&!confirm('¿Desvincular Authentik y cerrar las sesiones iniciadas por esa vía? El acceso local seguirá disponible.'))return;
        if(!data.linked&&options.beforeRedirect&&!options.beforeRedirect())return;
        action.disabled=true;password.disabled=true;const secret=password.value;password.value='';
        try{
          const result=await options.request('me/authentik/'+(data.linked?'unlink':'start'),{password:secret});
          if(!panel.isConnected)return;
          if(data.linked){status.textContent='Desvinculado. Si esta sesión usaba Authentik, vuelve a entrar con tu contraseña local.';await profile(root,account,options);panel.remove();}
          else location.assign(result.url);
        }catch(error){status.textContent=error.message;action.disabled=false;password.disabled=false;}
      },data.linked?'':'primary');panel.append(action,status);status.textContent='';
    }catch(error){status.textContent='No se pudo leer la vinculación: '+error.message;panel.append(button('Volver a comprobar',()=>{profile(root,account,options);panel.remove();}));}
  }

  async function config(root,options){
    const panel=make('section','','form-section settings-section authentik-config');panel.id='authentik-settings';panel.append(make('h3','Acceso e identidad · Authentik'));
    panel.append(make('p','Conecta tu proveedor OIDC autohospedado. Los roles y dispositivos se administran en Parental.'));root.append(panel);
    const status=feedback();status.textContent='Leyendo configuración…';panel.append(status);
    try{
      let cfg=await options.request('authentik/config');if(!panel.isConnected)return;
      const fields=make('div');panel.insertBefore(fields,status);
      const label=make('label','','toggle'),enabled=make('input');enabled.type='checkbox';enabled.checked=!!cfg.enabled;label.append(make('span','Habilitar inicio de sesión con Authentik'),enabled);fields.append(label);
      const issuer=field(fields,'Issuer esperado',cfg.issuer||'');issuer.placeholder='https://auth.example.com/application/o/parental/';
      const discovery=field(fields,'URL de descubrimiento OIDC',cfg.discovery_url||'');discovery.placeholder='https://auth.example.com/application/o/parental/.well-known/openid-configuration';
      const id=field(fields,'Client ID',cfg.client_id||''),secret=field(fields,'Client secret (vacío conserva el guardado)','','password');secret.autocomplete='new-password';secret.placeholder=cfg.secret_set?'Secreto guardado':'';
      const publicURL=field(fields,'URL pública HTTPS de Parental',cfg.public_url||'');publicURL.placeholder=location.origin;
      const callback=field(fields,'Redirect URI para copiar en Authentik',cfg.callback_url||'');callback.readOnly=true;
      publicURL.addEventListener('input',()=>{callback.value=publicURL.value.replace(/\/$/,'')+'/api/auth/oidc/callback';});
      const password=field(fields,'Tu contraseña local para guardar cambios','','password');
      fields.addEventListener('input',()=>options.draft?.());
      const actions=make('div','','identity-actions'),save=button('Guardar Authentik',async()=>{
        if(!password.value){status.textContent='Confirma tu contraseña local para guardar.';password.focus();return;}
        const body={enabled:enabled.checked,issuer:issuer.value,discovery_url:discovery.value,client_id:id.value,client_secret:secret.value,public_url:publicURL.value,password:password.value};
        save.disabled=true;for(const input of fields.querySelectorAll('input'))input.disabled=true;status.textContent='Guardando…';
        try{cfg=await options.request('authentik/config',body);if(!panel.isConnected)return;password.value='';secret.value='';secret.placeholder=cfg.secret_set?'Secreto guardado':'';options.clean?.();status.textContent='Configuración guardada. Se han cerrado las sesiones de Authentik anteriores; el acceso local sigue disponible.';}
        catch(error){status.textContent='No se pudo guardar: '+error.message;}
        finally{save.disabled=false;for(const input of fields.querySelectorAll('input'))input.disabled=false;}
      },'primary');
      const test=button('Probar configuración guardada',async()=>{test.disabled=true;status.textContent='Comprobando descubrimiento y claves…';try{const result=await options.request('authentik/test',{});status.textContent=result.message;}catch(error){status.textContent='No se pudo verificar: '+error.message;}finally{test.disabled=false;}});
      actions.append(save,test);panel.append(actions,make('p','En Authentik crea una aplicación con proveedor OAuth2/OIDC confidencial, Authorization Code, PKCE S256 y clave de firma asimétrica. Registra la Redirect URI exacta. Después vincula cada cuenta desde Mi perfil.'));
      const help=make('a','Guía de configuración');help.href='https://github.com/jesusgarrigues/parental/blob/main/docs/authentik.md';help.target='_blank';help.rel='noopener noreferrer';panel.append(help);status.textContent='';
    }catch(error){status.textContent='No se pudo leer la configuración: '+error.message;}
  }

  function userLink(root,user,options){
    root.replaceChildren();if(!user)return;
    root.append(make('p','Authentik: '+(user.authentik_linked?'Vinculado':'Sin vincular. La persona debe entrar con su contraseña local y vincular su identidad desde Mi perfil.')));
    if(!user.authentik_linked)return;
    const password=field(root,'Tu contraseña local de administrador para desvincular','','password'),status=feedback();
    const b=button('Desvincular Authentik de '+user.username,async()=>{if(!password.value){status.textContent='Confirma tu contraseña local.';return;}if(!confirm('¿Desvincular Authentik de '+user.username+'?'))return;b.disabled=true;try{await options.request('me/authentik/unlink',{user_id:user.id,password:password.value});password.value='';user.authentik_linked=false;userLink(root,user,options);}catch(error){status.textContent=error.message;b.disabled=false;}});root.append(b,status);
  }
  window.ParentalAuthentik={login,profile,config,userLink};
})();
