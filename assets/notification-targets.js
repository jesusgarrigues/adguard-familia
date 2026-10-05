// Shared by the page and the service worker; only internal, inert navigation targets.
(() => {
  function normalize(value){
    if(!value||typeof value!=='object')return null;
    if(value.kind==='request'){
      const id=typeof value.id==='string'&&/^[1-9]\d{0,14}$/.test(value.id)?Number(value.id):value.id;
      return typeof id==='number'&&Number.isSafeInteger(id)&&id>0?{kind:'request',id}:null;
    }
    if(value.kind==='client'&&typeof value.client==='string'&&typeof value.service==='string'&&value.client.trim()&&value.client.length<=256&&value.service.length<=128&&value.service&&!/[\u0000-\u001f]/.test(value.client+value.service))return {kind:'client',client:value.client,service:value.service};
    return null;
  }
  function url(value){const target=normalize(value);if(!target)return '/';
    if(target.kind==='request')return '/?view=requests#request='+target.id;
    return '/?view=clients#'+new URLSearchParams({client:target.client,service:target.service});
  }
  function fromURL(address){try{const u=new URL(address,'https://parental.invalid'),params=new URLSearchParams(u.hash.slice(1));
    if(params.has('request'))return normalize({kind:'request',id:params.get('request')});
    return normalize({kind:'client',client:params.get('client'),service:params.get('service')});
  }catch{return null;}}
  globalThis.ParentalTargets={normalize,url,fromURL};
})();
