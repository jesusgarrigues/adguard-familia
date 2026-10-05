/* Alert preferences and explicit authorization. DNS policy stays on the server. */
(() => {
  const make=(tag,text='',cls='')=>{const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n;};
  const action=(label,fn,cls='')=>{const n=make('button',label,cls);n.type='button';n.onclick=fn;return n;};
  const protections=[['@filtering','Filtrado DNS general'],['@parental','Control parental'],['@safebrowsing','Navegación segura'],['@safesearch','Búsqueda segura']];
  const clone=value=>JSON.parse(JSON.stringify(value));
  async function settings(root,options){
    if(!['admin','responsable'].includes(options.user.role))return;
    const section=make('section','','form-section settings-section blocked-alert-settings');section.id='blocked-alert-settings';
    section.append(make('h3','Intentos bloqueados'),make('p','Elige qué servicios te avisan y personaliza cada cliente. Esta selección solo afecta a los avisos; no cambia los bloqueos de AdGuard.'));
    const feedback=make('p','Cargando preferencias…','profile-feedback');feedback.setAttribute('role','status');section.append(feedback);root.append(section);
    try{
      const data=await options.request('me/notifications');if(!section.isConnected)return;
      const draft=clone(data.preferences),form=make('form');form.onsubmit=e=>e.preventDefault();
      const mark=()=>{options.draft();feedback.textContent='Hay cambios sin guardar.';};
      function editor(container,value,id){
        const label=make('label','Avisar de servicios'),mode=make('select');mode.id=id+'-mode';label.htmlFor=mode.id;
        for(const [key,title] of [['all','Todos los servicios bloqueados'],['selected','Solo los servicios seleccionados'],['none','Ningún servicio']]){const option=make('option',title);option.value=key;option.selected=value.mode===key;mode.append(option);}
        container.append(label,mode);
        const picker=make('div','','alert-service-picker'),search=make('input');search.type='search';search.placeholder='Buscar servicios…';search.setAttribute('aria-label','Buscar servicios de avisos');picker.append(search);
        const groups=make('div','','grouped-service-picker');
        for(const [category,title] of options.categories){
          const services=data.services.filter(s=>options.category(s.id)===category).sort((a,b)=>a.name.localeCompare(b.name,'es'));if(!services.length)continue;
          const details=make('details','','service-category'),summary=make('summary',title+' · '+services.length),grid=make('div','','service-picker');
          for(const service of services){const item=make('label'),check=make('input');check.type='checkbox';check.checked=value.services.includes(service.id);check.dataset.alertService=service.id;item.dataset.search=(service.name+' '+service.id).toLowerCase();
            check.onchange=()=>{value.services=check.checked?[...new Set([...value.services,service.id])]:value.services.filter(s=>s!==service.id);mark();};item.append(check,options.icon(service.id),make('span',service.name));grid.append(item);}
          details.append(summary,grid);groups.append(details);
        }
        search.oninput=()=>{const query=search.value.toLowerCase();for(const group of groups.children){let count=0;for(const item of group.querySelectorAll('label')){item.hidden=!item.dataset.search.includes(query);if(!item.hidden)count++;}group.hidden=!count;if(query)group.open=true;}};
        picker.append(groups);container.append(picker);
        const display=()=>{picker.hidden=value.mode!=='selected';for(const check of picker.querySelectorAll('input[type=checkbox]'))check.disabled=picker.hidden;};
        mode.onchange=()=>{value.mode=mode.value;display();mark();};display();
        const extra=make('details','','alert-protections');extra.append(make('summary','Otros bloqueos · opcionales'));
        for(const [key,title] of protections){const label=make('label','','alert-checkbox'),check=make('input');check.type='checkbox';check.checked=value.protections.includes(key);check.dataset.alertProtection=key;
          check.onchange=()=>{value.protections=check.checked?[...value.protections,key]:value.protections.filter(s=>s!==key);mark();};label.append(check,make('span',title));extra.append(label);}
        container.append(extra);
      }
      const general=make('div','','alert-defaults');general.append(make('h4','Selección general para tus clientes'));editor(general,draft,'alert-default');form.append(general);
      const intervalLabel=make('label','Intervalo mínimo entre avisos del mismo cliente y servicio'),interval=make('input');interval.type='number';interval.min=5;interval.max=1440;interval.step=1;interval.id='alert-cooldown';interval.value=draft.cooldown_minutes;intervalLabel.htmlFor=interval.id;
      interval.oninput=()=>{draft.cooldown_minutes=Number(interval.value);mark();};form.append(intervalLabel,interval,make('p','Los intentos repetidos se agrupan. Las solicitudes de tiempo tienen sus propios avisos.','notification-scope'));
      const clientGroup=make('details','','alert-client-group');clientGroup.append(make('summary','Personalizar por cliente · '+data.clients.length));
      for(const [index,client] of data.clients.entries()){
        const details=make('details','','alert-client'),summary=make('summary',client.name+(draft.clients[client.name]?' · Personalizado':' · General'));details.dataset.alertClient=client.name;
        details.append(summary);let initialized=false;
        details.addEventListener('toggle',()=>{if(!details.open||initialized)return;initialized=true;
          const label=make('label','','alert-checkbox'),inherit=make('input');inherit.type='checkbox';inherit.checked=!draft.clients[client.name];inherit.dataset.alertInherit=client.name;label.append(inherit,make('span','Usar la selección general de avisos'));details.append(label);
          if(client.ignore_querylog)details.append(make('p','Este cliente está excluido del registro de AdGuard; no se pueden detectar sus consultas.','notice warning'));
          const custom=make('div');details.append(custom);let local=draft.clients[client.name]||clone({mode:draft.mode,services:draft.services,protections:draft.protections});
          const render=()=>{custom.replaceChildren();custom.hidden=inherit.checked;if(!inherit.checked){draft.clients[client.name]=local;editor(custom,local,'alert-client-'+index);}else delete draft.clients[client.name];summary.textContent=client.name+(inherit.checked?' · General':' · Personalizado');};
          inherit.onchange=()=>{render();mark();};render();
        });clientGroup.append(details);
      }
      form.append(clientGroup);
      const save=action('Guardar avisos',async()=>{
        if(!interval.checkValidity()){feedback.textContent='El intervalo debe estar entre 5 y 1440 minutos.';interval.reportValidity();return;}
        const controls=[...form.querySelectorAll('input,select,button')].map(n=>[n,n.disabled]);for(const [n]of controls)n.disabled=true;
        try{const saved=await options.request('me/notifications',draft);if(!section.isConnected)return;options.clean();options.saved(saved);feedback.textContent='Avisos guardados. Se aplicarán a nuevos intentos; el historial no se reenvía.';}
        catch(error){feedback.textContent='No se pudo guardar: '+error.message;}
        finally{for(const [n,disabled]of controls)n.disabled=disabled;}
      },'primary');save.id='alert-save';form.append(save);section.insertBefore(form,feedback);feedback.textContent='Los otros bloqueos son opcionales. Las solicitudes de tiempo mantienen sus avisos. Se entregan mientras el panel está abierto.';
    }catch(error){feedback.textContent='No se pudieron cargar los avisos: '+error.message;section.append(action('Reintentar',()=>{section.remove();settings(root,options);}));}
  }
  function close(force=false){const node=document.getElementById('blocked-authorization');if(!node)return true;if(force!==true&&node.dataset.pending==='true')return false;node.remove();close.previous?.focus();return true;}
  function authorize(target,options){
    close(true);const client=options.state.clients.find(c=>c.name===target.client);if(!client)return;
    const previous=document.activeElement;close.previous=previous;
    const backdrop=make('div','','adguard-modal-backdrop authorization-backdrop');backdrop.id='blocked-authorization';
    const modal=make('section','','adguard-modal authorization-modal');modal.setAttribute('role','dialog');modal.setAttribute('aria-modal','true');modal.setAttribute('aria-labelledby','blocked-authorization-title');
    const title=make('h2','Permitir '+options.name(target.service));title.id='blocked-authorization-title';
    const head=make('div','','row authorization-heading'),identity=make('div','','authorization-identity');identity.append(options.icon(target.service),title);const dismiss=action('Cerrar',()=>close(),'ghost');head.append(identity,dismiss);
    modal.append(head,make('p',target.client,'authorization-client'));
    const event=options.state.events.find(e=>e.client===target.client&&e.service===target.service&&e.kind==='blocked');
    if(event)modal.append(make('p','Consulta bloqueada · '+new Date(event.time*1000).toLocaleString('es-ES',{timeZone:'Europe/Madrid'})+(event.domain?' · '+event.domain:''),'authorization-event'));
    modal.append(make('p','Una consulta DNS puede proceder de actividad en segundo plano. El permiso solo se aplicará cuando lo confirmes.','notification-scope'));
    const current=options.state.effective[target.client],base=options.state.base_effective[target.client];
    const restricted=config=>target.service==='@safesearch'?config?.safe_search?.enabled:target.service==='@filtering'?config?.filtering_enabled:target.service==='@parental'?config?.parental_enabled:target.service==='@safebrowsing'?config?.safebrowsing_enabled:config?.blocked_services?.includes(target.service);
    const lease=options.state.leases.find(l=>l.client===target.client&&l.service===target.service&&l.expires>Date.now()/1000);
    const feedback=make('p','','profile-feedback');feedback.setAttribute('role','status');feedback.id='authorization-feedback';
    if(lease){modal.append(make('p','Ya tiene un permiso temporal hasta '+new Date(lease.expires*1000).toLocaleTimeString('es-ES',{timeZone:'Europe/Madrid'}),'notice'));}
    else if(!restricted(current))modal.append(make('p','La restricción ya no está activa en la configuración actual.','notice'));
    const mayGrant=['admin','responsable'].includes(options.user.role),mayRequest=options.user.role==='solicitante';
    const permitted=restricted(base)&&restricted(current)&&!lease;
    if(!mayGrant&&!mayRequest)modal.append(make('p','Tu cuenta tiene acceso de consulta.'));
    if((mayGrant||mayRequest)&&permitted){
      const label=make('label','Duración del permiso'),minutes=make('select');minutes.id='authorization-minutes';label.htmlFor=minutes.id;
      for(const value of [5,10,15,20,30,60,120].filter(m=>options.user.role!=='responsable'||m<=options.user.max_minutes)){const option=make('option',value+' minutos');option.value=value;option.selected=value===20;minutes.append(option);}
      modal.append(label,minutes);
      let reason=null;if(mayRequest){const reasonLabel=make('label','Motivo (opcional)');reason=make('textarea');reason.id='authorization-reason';reason.maxLength=1000;reasonLabel.htmlFor=reason.id;modal.append(reasonLabel,reason);}
      const submit=action(mayGrant?'Autorizar tiempo':'Solicitar aprobación',async()=>{
        const selected=Number(minutes.value);if(!selected)return;
        backdrop.dataset.pending='true';for(const input of modal.querySelectorAll('input,select,textarea,button'))input.disabled=true;feedback.textContent=mayGrant?'Aplicando permiso…':'Enviando solicitud…';
        try{const body={client:target.client,service:target.service,minutes:selected};if(reason)body.reason=reason.value;if(mayGrant)body.from_blocked_event=true;
          await options.request(mayGrant?'permit':'request',body);
          feedback.textContent=mayGrant?'Permiso concedido: '+selected+' minutos. Las restricciones se restaurarán al terminar.':'Solicitud enviada. Un responsable debe aprobarla.';submit.hidden=true;minutes.disabled=true;if(reason)reason.disabled=true;
          await options.refresh();
        }catch(error){feedback.textContent='No se pudo completar: '+error.message;submit.disabled=false;minutes.disabled=false;if(reason)reason.disabled=false;}
        finally{backdrop.dataset.pending='false';dismiss.disabled=false;}
      },'primary');submit.id='authorization-submit';if(!minutes.options.length){submit.disabled=true;feedback.textContent='Tu límite de aprobación no permite estas duraciones.';}modal.append(submit);
    }
    modal.append(feedback);backdrop.append(modal);backdrop.onclick=e=>{if(e.target===backdrop)close();};backdrop.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();close();}if(e.key==='Tab'){const nodes=[...modal.querySelectorAll('button,input,select,textarea')].filter(n=>!n.disabled&&n.getClientRects().length);const first=nodes[0],last=nodes.at(-1);if(first&&e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(last&&!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}};document.body.append(backdrop);dismiss.focus();
  }
  window.ParentalBlockedAlerts={settings,authorize,close};
})();
