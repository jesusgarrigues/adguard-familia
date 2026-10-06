/* Polling is independent of screen rendering and unsaved forms. */
(() => {
  let callbacks={},current=null,device=null,registered=false,push=false,running=false,items=[],diagnostic=null,lastError='';
  const identifiers=new Map();
  const make=(tag,text='')=>{const n=document.createElement(tag);n.textContent=text;return n;};
  function id(account){if(identifiers.has(account.id))return identifiers.get(account.id);const key='parental-alert-device-'+account.id;let value;try{value=localStorage.getItem(key);}catch{}
    if(!/^[a-zA-Z0-9_-]{16,80}$/.test(value||'')){value=crypto.randomUUID();try{localStorage.setItem(key,value);}catch{}}identifiers.set(account.id,value);return value;}
  const registration=()=>navigator.serviceWorker?.getRegistration?.();
  function status(){if(lastError)return lastError;
    const delivery=diagnostic?.last_delivery;
    const labels={pending:'Aviso pendiente',sending:'Enviando aviso',retry:'Entrega fallida; se volverá a intentar',failed:'Entrega fallida: vuelve a activar los avisos',accepted:'Último aviso aceptado por el navegador o proveedor',skipped:'Envío omitido: leído, resuelto, antiguo o fuera de preferencias'};
    return (push?'Envío desde el servidor activado, también con Parental cerrada.':'Sin Push registrado: entrega automática solo con Parental abierta. Pulsa Activar avisos para completar la activación.')+(delivery?' '+(labels[delivery.status]||delivery.status)+(delivery.error?' ('+delivery.error+')':''):'');}
  function renderStatus(){for(const n of document.querySelectorAll('[data-auto-notification-status]'))n.textContent=status();for(const n of document.querySelectorAll('[data-auto-notification-detail]'))n.textContent=diagnostic?JSON.stringify(diagnostic,null,2):'Todavía no hay diagnóstico de este dispositivo.';window.ParentalNotifications?.update();}
  async function poll(){const account=callbacks.account?.();if(!account){current=null;registered=false;items=[];push=false;window.ParentalUI?.setAlerts(0,null);return;}if(running)return;running=true;
    try{
      if(current!==account.id){current=account.id;device=id(account);registered=false;push=false;items=[];lastError='';}
      const own=current;
      if(!registered){const reg=await registration(),sub=await reg?.pushManager?.getSubscription?.();if(callbacks.account?.()?.id!==own)return;
        const saved=await callbacks.request('me/alerts/device',{device,subscription:sub?.toJSON()||null});if(callbacks.account?.()?.id!==own)return;registered=true;push=saved.push;}
      const data=await callbacks.request('me/alerts?device='+encodeURIComponent(device));if(callbacks.account?.()?.id!==own)return;
      items=data.items||[];diagnostic=data.diagnostic;push=!!diagnostic?.push;lastError='';window.ParentalUI?.setRequests(data.requests||[],account);window.ParentalUI?.setAlerts(data.unread||0,account);renderStatus();renderLists();
      if(!push&&window.ParentalNotifications?.state().enabled)for(const item of data.deliveries||[]){
        if(callbacks.account?.()?.id!==own)return;const claim=await callbacks.request('me/alerts/result',{device,id:item.id,status:'claim'});if(!claim.claimed)continue;
        const title=item.kind==='request'?'Nueva solicitud de '+item.detail.username:item.client+' · '+callbacks.name(item.service);
        const body=item.kind==='request'?item.client+' · '+item.detail.minutes+' minutos':'Consulta bloqueada. Pulsa para revisar y autorizar tiempo.';
        const accepted=await window.ParentalNotifications.notify(title,{body,tag:'parental-alert-'+item.id,target:item.target});if(callbacks.account?.()?.id!==own)return;
        await callbacks.request('me/alerts/result',{device,id:item.id,status:accepted?'accepted':'failed'});
      }
    }catch(error){lastError='No se pudo comprobar o entregar los avisos: '+error.message;renderStatus();}finally{running=false;}}
  async function activate(){const account=callbacks.account?.();if(!account)throw Error('Inicia sesión para activar los avisos');device=id(account);
    const data=await callbacks.request('me/alerts'),reg=await registration();if(!reg?.active||!reg.pushManager)throw Error('El navegador no ofrece Push en este modo. En iPhone abre Parental desde el icono instalado.');
    let sub=await reg.pushManager.getSubscription();const bytes=Uint8Array.from(atob(data.public_key.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-data.public_key.length%4)%4)),c=>c.charCodeAt(0));
    if(sub&&diagnostic?.last_delivery?.error==='push_subscription_expired'){await sub.unsubscribe();sub=null;}
    if(sub&&sub.options?.applicationServerKey){const old=new Uint8Array(sub.options.applicationServerKey);if(old.length!==bytes.length||old.some((v,i)=>v!==bytes[i])){await sub.unsubscribe();sub=null;}}
    if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:bytes});if(callbacks.account?.()?.id!==account.id){await sub.unsubscribe();throw Error('La sesión ha cambiado; vuelve a activar los avisos');}
    const saved=await callbacks.request('me/alerts/device',{device,subscription:sub.toJSON()});current=account.id;registered=true;push=saved.push;lastError='';renderStatus();return true;}
  async function disconnect(){const account=callbacks.account?.();if(account)await callbacks.request('me/alerts/disconnect',{device:id(account)});const reg=await registration(),sub=await reg?.pushManager?.getSubscription?.();if(sub)await sub.unsubscribe();current=null;registered=false;push=false;items=[];window.ParentalUI?.setAlerts(0,null);}
  async function read(identifier){await callbacks.request('me/alerts/read',{id:identifier});await poll();}
  async function readTarget(target){if(target?.alert_id)try{await read(target.alert_id);}catch(error){lastError='No se pudo marcar el aviso leído: '+error.message;renderStatus();}}
  function renderLists(){for(const root of document.querySelectorAll('[data-alert-inbox]')){root.replaceChildren();const row=make('div');row.className='row';row.append(make('h2','Avisos'));
    const all=make('button','Marcar todos como leídos');all.type='button';all.disabled=!items.some(i=>i.kind==='blocked'&&!i.read_at);all.onclick=async()=>{all.disabled=true;try{await read(null);}catch(e){root.prepend(make('p',e.message));all.disabled=false;}};row.append(all);root.append(row);
    root.append(make('p','Se conservan hasta que los revises, durante un máximo de 30 días. Leer avisos no concede permisos.'));
    const blocks=items.filter(i=>i.kind==='blocked');if(!blocks.length)root.append(make('p','Sin avisos de bloqueos seleccionados. La actividad completa aparece debajo.'));
    for(const item of blocks){const card=make('article');card.className='card event '+(item.read_at?'':'blocked');card.append(make('strong',item.client+' · '+callbacks.name(item.service)+(item.read_at?'':' · Nuevo')));card.append(make('p',new Date(item.created*1000).toLocaleString()+(item.detail.domain?' · '+item.detail.domain:'')));const button=make('button','Revisar permiso');button.type='button';button.onclick=()=>callbacks.navigate(item.target);card.append(button);root.append(card);}root.append(make('h2','Actividad reciente'));}}
  function inbox(root){const section=make('section');section.dataset.alertInbox='';root.append(section);renderLists();poll();}
  async function testPush(){if(!push)throw Error('Activa primero el envío desde el servidor');await callbacks.request('me/alerts/test',{device});await poll();}
  function init(options){callbacks=options;window.ParentalNotifications?.attach?.({activate,connected:()=>push,status,testPush});setInterval(poll,10000);document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')poll();});}
  window.ParentalAlertCenter={init,poll,inbox,readTarget,disconnect,activate,status,testPush};
})();
