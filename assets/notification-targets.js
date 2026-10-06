// Shared by the page and the service worker; only internal, inert navigation targets.
(() => {
  function normalize(value){
    if(!value||typeof value!=='object')return null;
    if(value.kind==='request'){
      const id=typeof value.id==='string'&&/^[1-9]\d{0,14}$/.test(value.id)?Number(value.id):value.id;
      return typeof id==='number'&&Number.isSafeInteger(id)&&id>0?withAlert({kind:'request',id},value):null;
    }
    if(value.kind==='users')return withAlert({kind:'users'},value);
    if(value.kind==='client'&&typeof value.client==='string'&&typeof value.service==='string'&&value.client.trim()&&value.client.length<=256&&value.service.length<=128&&value.service&&!/[\u0000-\u001f]/.test(value.client+value.service))return withAlert({kind:'client',client:value.client,service:value.service},value);
    return null;
  }
  function withAlert(target,value){const id=Number(value.alert_id);if(Number.isSafeInteger(id)&&id>0)target.alert_id=id;return target;}
  function url(value){const target=normalize(value);if(!target)return '/';
    const alert=target.alert_id?'&alert='+target.alert_id:'';
    if(target.kind==='request')return '/?view=requests#request='+target.id+alert;
    if(target.kind==='users')return '/?view=users'+(target.alert_id?'#alert='+target.alert_id:'');
    return '/?view=clients#'+new URLSearchParams({client:target.client,service:target.service})+alert;
  }
  function fromURL(address){try{const u=new URL(address,'https://parental.invalid'),params=new URLSearchParams(u.hash.slice(1));
    if(u.searchParams.get('view')==='users')return normalize({kind:'users',alert_id:params.get('alert')});
    if(params.has('request'))return normalize({kind:'request',id:params.get('request'),alert_id:params.get('alert')});
    return normalize({kind:'client',client:params.get('client'),service:params.get('service'),alert_id:params.get('alert')});
  }catch{return null;}}
  globalThis.ParentalTargets={normalize,url,fromURL};
})();
