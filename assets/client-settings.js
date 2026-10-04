const deviceIconCatalog=[['monitor','Ordenador'],['laptop','Portátil'],['smartphone','Móvil'],['tablet','Tableta'],['gamepad-2','Consola'],['tv','Televisor'],['router','Router'],['printer','Impresora'],['speaker','Altavoz'],['headphones','Auriculares'],['watch','Reloj'],['server','Servidor']];
function automaticDeviceIcon(client){
 if(client.ui_auto_icon)return client.ui_auto_icon;
 const tags=client.tags||[],text=(client.name+' '+(client.model||'')).toLowerCase();
 const kinds={'device_phone':'smartphone','device_tablet':'tablet','device_tv':'tv','device_router':'router','device_printer':'printer','device_gameconsole':'gamepad-2'};
 for(const tag of tags)if(kinds[tag])return kinds[tag];
 for(const [pattern,icon]of [[/ipad|tablet/,'tablet'],[/iphone|android|móvil|movil|phone/,'smartphone'],[/macbook|laptop|portátil|portatil/,'laptop'],[/imac|ordenador|desktop|\bpc\b/,'monitor'],[/switch|xbox|playstation|consola/,'gamepad-2'],[/televisi|\btv\b/,'tv'],[/router|wifi/,'router'],[/impresora|printer/,'printer'],[/altavoz|speaker/,'speaker'],[/auriculares|headphone/,'headphones'],[/reloj|watch/,'watch']])if(pattern.test(text))return icon;
 return tags.includes('device_pc')?'monitor':'server';
}
function clientDeviceIcon(client,consoleDevice=false){
 const id=client.ui_icon||(consoleDevice?'gamepad-2':automaticDeviceIcon(client));
 const kind=deviceIconCatalog.find(([key])=>key===id)?id:'server',wrap=el('span','','computer device-icon icon-'+kind),img=el('img');
 img.src='/assets/icons/'+kind+'.svg';img.alt='';img.setAttribute('aria-hidden','true');wrap.setAttribute('aria-label',deviceIconCatalog.find(([key])=>key===kind)[1]);wrap.append(img);return wrap;
}
function canChangeClientIcon(){return ['admin','responsable'].includes(me?.role)}
function openClientIconPicker(client,key,consoleDevice=false){
 if($('icon-selector'))return;
 const previous=document.activeElement,backdrop=el('div','','icon-selector');backdrop.id='icon-selector';
 const panel=el('section','','icon-selector-panel');panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');panel.setAttribute('aria-labelledby','icon-selector-title');
 const title=el('h2','Cambiar icono');title.id='icon-selector-title';let choice=client.ui_icon||'auto';
 const feedback=el('div','','client-feedback');feedback.hidden=true;feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');
 const grid=el('div','','icon-selector-grid'),buttons=[];
 for(const [id,label]of [['auto','Automático'],...deviceIconCatalog]){const b=button('',()=>{choice=id;for(const btn of buttons)btn.setAttribute('aria-pressed',String(btn.dataset.icon===choice))},'icon-choice');b.dataset.icon=id;b.setAttribute('aria-pressed',String(id===choice));b.append(clientDeviceIcon({...client,ui_icon:id==='auto'?null:id},consoleDevice),el('span',label));buttons.push(b);grid.append(b)}
 let saving=false;const close=()=>{if(saving)return;backdrop.remove();previous?.focus()};
 const save=button('Guardar icono',async()=>{if(saving)return;saving=true;save.disabled=true;save.textContent='Guardando…';feedback.hidden=false;feedback.className='client-feedback';feedback.textContent='Guardando icono…';try{await request('client/icon',{client:key,icon:choice});client.ui_icon=choice==='auto'?null:choice;const current=consoleDevice?nintendoState.devices.find(d=>nintendoDeviceKey(d)===key):state?.clients.find(c=>c.name===key);if(current)current.ui_icon=client.ui_icon;renderClientGrid();if(consoleDevice){renderNintendoClientGrid();openNintendoDialog(key)}else{$('adguard-dialog-title')?.previousElementSibling?.replaceWith(clientDeviceIcon(client))}saving=false;close();msg('Icono guardado.')}catch(e){feedback.className='client-feedback error';feedback.textContent=e.message||'No se pudo guardar el icono.'}finally{saving=false;save.disabled=false;save.textContent='Guardar icono'}},'primary');
 const toolbar=el('div','','toolbar');toolbar.append(button('Cancelar',close),save);panel.append(title,el('p','El icono se conserva en todos tus dispositivos.'),grid,feedback,toolbar);backdrop.append(panel);document.body.append(backdrop);
 backdrop.onclick=e=>{if(e.target===backdrop)close()};backdrop.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close()}if(e.key==='Tab'){const nodes=[...panel.querySelectorAll('button')].filter(n=>!n.disabled),first=nodes[0],last=nodes.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}};buttons[0].focus();
}
function setClientFeedback(root,text,kind='success'){
 root.hidden=false;root.className='client-feedback'+(kind==='error'?' error':kind==='warning'?' warning':'');root.textContent=text;
 root.setAttribute('role',kind==='error'?'alert':'status');root.scrollIntoView?.({block:'nearest'});if(kind==='error')root.focus();
}
function clientConfigurationPatch(){
 const patch={name:$('c-name').value.trim(),ids:lines('c-ids'),tags:lines('c-tags'),use_global_settings:$('c-global').checked,use_global_blocked_services:$('c-global-services').checked,upstreams:lines('c-upstreams'),upstreams_cache_size:Number($('c-cache').value),upstreams_cache_enabled:$('c-upstreams_cache_enabled').checked,ignore_querylog:$('c-ignore_querylog').checked,ignore_statistics:$('c-ignore_statistics').checked};
 if(!patch.name)throw Error('Indica un nombre para el cliente.');if(!patch.ids.length)throw Error('Indica al menos un identificador para el cliente.');
 if(!Number.isSafeInteger(patch.upstreams_cache_size)||patch.upstreams_cache_size<0)throw Error('El tamaño de caché debe ser un número entero igual o mayor que cero.');
 if(!patch.use_global_settings){for(const k of ['filtering_enabled','parental_enabled','safebrowsing_enabled'])patch[k]=$('c-'+k).checked;patch.safe_search=getSafe('c-safe-')}
 if(!patch.use_global_blocked_services){patch.blocked_services=getServices('client');patch.blocked_services_schedule=getSchedule('c-schedule-')}
 return patch;
}
function savedConfigurationMatches(actual,patch){
 const same=(value,wanted)=>Array.isArray(wanted)?Array.isArray(value)&&JSON.stringify([...value].sort())===JSON.stringify([...wanted].sort()):wanted&&typeof wanted==='object'?!!value&&Object.entries(wanted).every(([k,v])=>same(value[k],v)):value===wanted;
 return !!actual&&Object.entries(patch).every(([key,value])=>same(actual[key],value));
}
async function clientSettingsRequest(path,body){
 const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),30000);
 try{return await request(path,body,{signal:controller.signal})}catch(e){if(e.name==='AbortError')throw Error('La petición ha superado 30 segundos. No se pudo confirmar el resultado; comprueba el estado antes de volver a guardar.');throw e}finally{clearTimeout(timeout)}
}
async function saveClientConfiguration(form,feedback,save,inDialog){
 if(busy){setClientFeedback(feedback,'Hay otra operación en curso. Espera a que termine e inténtalo de nuevo.','warning');return}
 let patch;try{patch=form.acceptedPatch||clientConfigurationPatch()}catch(e){setClientFeedback(feedback,e.message,'error');return}
 const originalClient=selected,adding=!originalClient,checking=!!form.acceptedPatch;
 busy=true;dirty=true;save.disabled=true;save.textContent=checking?'Comprobando…':'Guardando…';form.dataset.saving='true';
 setClientFeedback(feedback,checking?'Comprobando la configuración guardada…':'Guardando la configuración en AdGuard…');
 const controls=[...form.querySelectorAll('input,textarea,select')].map(node=>[node,node.disabled]);for(const [node]of controls)node.disabled=true;
 try{
  if(!checking){const result=await clientSettingsRequest(adding?'client/add':'client',{client:originalClient,patch});if(!result.ok)throw Error(result.error||'AdGuard no ha confirmado el guardado.');form.acceptedPatch=patch}
  let fresh;try{fresh=await clientSettingsRequest('state')}catch(e){setClientFeedback(feedback,'AdGuard ha aceptado el guardado, pero no se pudo verificar la configuración: '+e.message+' Pulsa «Comprobar guardado»; no se reenviará el cambio.','warning');return}
  const actual=fresh.base_clients?.[patch.name];if(!savedConfigurationMatches(actual,patch)){setClientFeedback(feedback,'AdGuard ha aceptado el guardado, pero la lectura todavía no coincide con los valores solicitados. Pulsa «Comprobar guardado» para consultar de nuevo sin reenviar el cambio.','warning');return}
  state=fresh;dirty=false;form.acceptedPatch=null;msg('Configuración guardada y comprobada en AdGuard.');
  if(inDialog){delete form.dataset.saving;closeAdGuardDialog(true)}page='clients';selected=null;render();
 }catch(e){setClientFeedback(feedback,e.message||'No se pudo guardar la configuración.','error')}
 finally{busy=false;delete form.dataset.saving;for(const [node,disabled]of controls)node.disabled=disabled;save.disabled=false;save.textContent=form.acceptedPatch?'Comprobar guardado':'Guardar configuración'}
}
