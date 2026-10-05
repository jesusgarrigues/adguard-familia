(() => {
  'use strict';
  let feedback='',failed=false;
  const ios=()=>/iPad|iPhone|iPod/.test(navigator.userAgent||'') || (navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
  const installed=()=>navigator.standalone===true||window.matchMedia?.('(display-mode: standalone)').matches===true;
  function state(){
    if(window.isSecureContext===false)return {enabled:false,available:false,label:'No disponibles',hint:'Abre Parental mediante HTTPS para activar los avisos.'};
    if(ios()&&!installed())return {enabled:false,available:false,label:'Instala Parental primero',hint:'En Safari: Compartir → Añadir a pantalla de inicio. Abre Parental desde su icono. Los avisos web requieren iOS/iPadOS 16.4 o posterior.'};
    if(!('Notification' in window))return {enabled:false,available:false,label:'No disponibles',hint:'Este navegador no ofrece notificaciones. Puedes usar un destino externo cuando esté configurado.'};
    const p=window.Notification.permission;
    if(p==='denied')return {enabled:false,available:false,label:'Bloqueados',hint:ios()?'Activa las notificaciones de Parental en Ajustes del iPhone y vuelve a abrir la app.':'Permite las notificaciones para este sitio en los ajustes del navegador.'};
    return {enabled:p==='granted',available:true,label:p==='granted'?'Permiso concedido':'Sin activar',hint:p==='granted'?'Puedes comprobar la entrega con «Probar aviso».':'Pulsa «Activar avisos» para solicitar permiso.'};
  }
  function update(){const s=state();for(const root of document.querySelectorAll('[data-notification-panel]')){
    root.querySelector('[data-notification-state]').textContent=s.label;
    root.querySelector('[data-notification-hint]').textContent=s.hint;
    const status=root.querySelector('[data-notification-feedback]');status.textContent=feedback;status.classList.toggle('notification-error',failed);
    const activate=root.querySelector('[data-notification-enable]');activate.disabled=!s.available||s.enabled;
    root.querySelector('[data-notification-test]').disabled=!s.enabled;
  }}
  function result(message,error=false){feedback=message;failed=error;update();return !error;}
  function bounded(promise){let timer;return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('La entrega ha tardado demasiado. Comprueba el navegador y vuelve a probar.')),4000);})]).finally(()=>clearTimeout(timer));}
  async function registration(){if(!navigator.serviceWorker?.getRegistration)return null;return bounded(navigator.serviceWorker.getRegistration());}
  async function notify(title,options={}){
    if(!state().enabled)return false;
    const target=window.ParentalTargets?.normalize(options.target);
    const destination=target?window.ParentalTargets.url(target):options.url==='/?view=requests'?'/?view=requests':'/';
    const config={body:options.body||'',icon:'/icon-192.png',badge:'/icon-192.png',tag:options.tag,data:{url:destination,target}};
    try{
      const reg=await registration();
      if(reg?.active&&typeof reg.showNotification==='function')await bounded(reg.showNotification(title,config));
      else if(!ios())new window.Notification(title,config);
      else throw Error('No se ha podido entregar el aviso. Cierra y abre Parental desde su icono; después pulsa «Probar aviso».');
      return true;
    }catch(error){return result('No se pudo mostrar el aviso: '+(error.message||'Error del navegador'),true);}
  }
  async function enable(){
    const current=state();if(!current.available)return result(current.hint,true);
    if(current.enabled)return result('El permiso ya está concedido. Usa «Probar aviso» para comprobarlo.');
    // Request permission directly from the click, before awaiting any service-worker work.
    try{const permission=await window.Notification.requestPermission();
      if(permission==='granted')return result('Permiso concedido. Pulsa «Probar aviso» para comprobar la entrega.');
      if(permission==='denied')return result(state().hint,true);
      return result('No se ha concedido permiso. Puedes volver a intentarlo.',true);
    }catch(error){return result('No se pudieron activar los avisos: '+(error.message||'Error del navegador'),true);}
  }
  function panel(root){
    root.dataset.notificationPanel='';
    const make=(tag,text,attr)=>{const n=document.createElement(tag);n.textContent=text;if(attr)n.setAttribute(attr,'');root.append(n);return n;};
    make('strong','','data-notification-state');make('p','','data-notification-hint');
    const status=make('p','','data-notification-feedback');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
    const activate=make('button','Activar avisos','data-notification-enable');activate.type='button';
    const test=make('button','Probar aviso','data-notification-test');test.type='button';
    const run=async(button,fn)=>{button.disabled=true;try{await fn();}finally{update();}};
    activate.onclick=()=>run(activate,enable);
    test.onclick=()=>run(test,async()=>{const ok=await notify('Parental · Aviso de prueba',{body:'La entrega de avisos funciona en este dispositivo.',tag:'parental-test'});if(ok)result('Aviso de prueba enviado al sistema. Comprueba el centro de notificaciones.');});
    make('p','Estos avisos funcionan mientras el panel está abierto. Los destinos externos se configuran por separado cuando estén disponibles.').className='notification-scope';update();
  }
  document.addEventListener?.('visibilitychange',update);
  window.ParentalNotifications={state,enable,notify,panel,update};
})();
