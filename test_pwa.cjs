const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const badges=[{},{}],navigation=[{setAttribute(key,value){this[key]=value}}],alertBadge={},alertNavigation=[{querySelector:()=>alertBadge,setAttribute(key,value){this[key]=value}}],badgeCalls=[];
const context=vm.createContext({window:{ParentalBadges:{update:(count,account)=>badgeCalls.push({count,account})}},navigator:{},document:{querySelectorAll:q=>q==='[data-request-count]'?badges:q==='.nav[data-page="activity"]'?alertNavigation:navigation,getElementById:()=>null},console,Date,Number});
vm.runInContext(fs.readFileSync('assets/app-shell.js','utf8'),context);
const ui=context.window.ParentalUI,now=Date.now()/1000;
const requests=[
 {id:1,status:'pending',client:'Emma',user_id:2,created:now},
 {id:2,status:'pending',client:'Martin',user_id:3,created:now},
 {id:3,status:'approved',client:'Emma',user_id:2,created:now},
 {id:4,status:'pending',client:'Emma',user_id:2,created:now-86401}
];
assert.equal(ui.countPending(requests,{id:1,role:'admin'}),2);
assert.equal(ui.countPending(requests,{id:4,role:'responsable',clients:['Emma']}),1);
assert.equal(ui.countPending(requests,{id:2,role:'solicitante',clients:['Emma','Martin']}),1);
assert.equal(ui.countPending(requests,{id:4,role:'responsable',clients:[]}),0);
assert.equal(ui.countPending(requests,null),0);
assert.equal(ui.countPending(requests,{role:'admin'},now+86401),0);
ui.setRequests(requests,{id:1,role:'admin'});assert.equal(badges[0].textContent,'2');assert.equal(badges[1].hidden,false);
ui.setAlerts(3,{id:1,role:'admin'});assert.equal(alertBadge.textContent,'3');assert.equal(badgeCalls.at(-1).count,5);
ui.setAlerts(0,{id:1,role:'admin'});assert.equal(alertBadge.hidden,true);assert.equal(badgeCalls.at(-1).count,2);
ui.setRequests(requests,{id:2,role:'solicitante'});assert.equal(badges[0].textContent,'1');
ui.setRequests([],null);assert.equal(badges[0].hidden,true);assert.equal(navigation[0]['aria-label'],'Solicitudes');
assert.equal(alertBadge.hidden,true);assert.equal(badgeCalls.at(-1).count,0);

(async()=>{
 const handlers={},storage=new Map(),deleted=[];let offline=false;
 const cache={async put(key,value){storage.set(key,value.clone())},async match(key){return storage.get(key)?.clone()}};
 const sw=vm.createContext({URL,URLSearchParams,Response,Promise,Set,console,
  self:{location:{origin:'https://parental.test'},addEventListener:(name,fn)=>handlers[name]=fn,skipWaiting:async()=>{},clients:{claim:async()=>{}}},
  caches:{open:async()=>cache,keys:async()=>['parental-static-old','other-app-cache'],delete:async key=>{deleted.push(key)}},
  fetch:async request=>{if(offline)throw Error('offline');const url=typeof request==='string'?request:request.url;return new Response('public resource '+url)}
 });
 sw.importScripts=(...paths)=>{for(const path of paths)vm.runInContext(fs.readFileSync(path.slice(1),'utf8'),sw);};
 vm.runInContext(fs.readFileSync('sw.js','utf8'),sw);
 const pushShown=[],pushBadges=[];
 sw.self.registration={showNotification:async(title,options)=>pushShown.push({title,options})};
 sw.self.navigator={setAppBadge:async n=>pushBadges.push(n),clearAppBadge:async()=>pushBadges.push(0)};
 sw.self.clients.matchAll=async()=>[];
 let pushed;handlers.push({data:{json:()=>({title:'TV · YouTube',body:'Servicio bloqueado',target:{kind:'client',client:'TV',service:'youtube',alert_id:13},badge_count:5})},waitUntil:p=>pushed=p});await pushed;
 assert.equal(pushShown[0].options.data.target.alert_id,13);assert.deepEqual(pushBadges,[5]);
 let promise;handlers.install({waitUntil:p=>promise=p});await promise;
 assert.ok(storage.has('/apple-touch-icon.png'));assert.ok(storage.has('/assets/parental.css'));
 assert.ok([...storage.keys()].every(key=>!key.startsWith('/api/')&&key!=='/'));
 handlers.activate({waitUntil:p=>promise=p});await promise;assert.deepEqual(deleted,['parental-static-old']);
 const posted=[],opened=[];let focused=0;
 sw.self.clients.matchAll=async()=>[{url:'https://parental.test/',visibilityState:'visible',postMessage:m=>posted.push(m),focus:async()=>{focused++}}];
 handlers.notificationclick({notification:{data:{target:{kind:'request',id:9},url:'https://evil.test/'},close(){}},waitUntil:p=>promise=p});await promise;
 assert.equal(posted[0].target.id,9);assert.equal(focused,1);
 sw.self.clients.matchAll=async()=>[];sw.self.clients.openWindow=async url=>opened.push(url);
 handlers.notificationclick({notification:{data:{target:{kind:'request',id:-1},url:'https://evil.test/'},close(){}},waitUntil:p=>promise=p});await promise;
 assert.equal(opened[0],'https://parental.test/');
 for(const request of [
  {method:'GET',url:'https://parental.test/api/requests',mode:'cors'},
  {method:'POST',url:'https://parental.test/api/request/review',mode:'cors'},
  {method:'GET',url:'https://other.test/icon-192.png',mode:'cors'},
  {method:'GET',url:'https://parental.test/private.json',mode:'cors'}
 ]){let intercepted=false;handlers.fetch({request,respondWith(){intercepted=true}});assert.equal(intercepted,false)}
 offline=true;
 handlers.fetch({request:{method:'GET',url:'https://parental.test/?view=requests',mode:'navigate'},respondWith:p=>promise=p});
 const fallback=await promise;assert.equal(fallback.headers.get('cache-control'),'no-store');assert.ok((await fallback.text()).includes('Sin conexión'));
 handlers.fetch({request:{method:'GET',url:'https://parental.test/icon-192.png?v=parental-1',mode:'cors'},respondWith:p=>promise=p});assert.ok((await (await promise).text()).includes('/icon-192.png'));
 console.log('PWA: scoped pending badges, expiry, offline assets and no private/API/action caching verified');
})().catch(e=>{console.error(e);process.exitCode=1});
