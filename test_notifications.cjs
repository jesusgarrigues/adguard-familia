const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
function env({ios=false,installed=false,secure=true,permission='default',register,request,constructorError=false,api=true}={}){
 const nodes=new Map(),out=[],get=k=>{if(!nodes.has(k))nodes.set(k,{textContent:'',disabled:false,classList:{toggle(){}}});return nodes.get(k)};
 function Notification(title,options){if(constructorError)throw Error('Constructor unsupported');out.push({title,options,method:'constructor'})}
 Notification.permission=permission;Notification.requestPermission=request||(async()=>{Notification.permission='granted';return 'granted'});
 const context=vm.createContext({window:{isSecureContext:secure,matchMedia:()=>({matches:installed}),...(api?{Notification}:{})},navigator:{userAgent:ios?'iPhone':'Desktop',standalone:installed,...(register?{serviceWorker:{getRegistration:register}}:{})},document:{addEventListener(){},querySelectorAll:()=>[{querySelector:get}]},console,Promise,setTimeout,clearTimeout});
 vm.runInContext(fs.readFileSync('assets/notifications.js','utf8'),context);return {ui:context.window.ParentalNotifications,out,nodes,Notification};
}
(async()=>{
 assert.equal(env({secure:false}).ui.state().available,false);assert.equal(env({ios:true}).ui.state().available,false);assert.ok(env({ios:true}).ui.state().hint.includes('16.4'));assert.equal(env({api:false}).ui.state().label,'No disponibles');
 const denied=env({permission:'denied',request:()=>{throw Error('must not prompt')}});assert.equal(await denied.ui.enable(),false);assert.equal(denied.ui.state().label,'Bloqueados');
 const rejected=env({request:async()=>{throw Error('permission fixture')}});assert.equal(await rejected.ui.enable(),false);assert.ok(rejected.nodes.get('[data-notification-feedback]').textContent.includes('permission fixture'));
 const desktop=env();assert.equal(await desktop.ui.enable(),true);assert.equal(desktop.ui.state().enabled,true);assert.equal(await desktop.ui.notify('Test',{url:'https://evil.test/'}),true);assert.equal(desktop.out[0].options.data.url,'/');
 const delivered=[];const ios=env({ios:true,installed:true,permission:'granted',register:async()=>({active:{},showNotification:async(title,options)=>delivered.push({title,options})})});
 assert.equal(await ios.ui.notify('Request',{url:'/?view=requests',tag:'request-3'}),true);assert.equal(ios.out.length,0);assert.equal(delivered[0].options.data.url,'/?view=requests');
 const broken=env({permission:'granted',register:async()=>{throw Error('registration fixture')}});assert.equal(await broken.ui.notify('Test'),false);assert.ok(broken.nodes.get('[data-notification-feedback]').textContent.includes('registration fixture'));
 const noWorker=env({ios:true,installed:true,permission:'granted'});assert.equal(await noWorker.ui.notify('Test'),false);assert.equal(noWorker.out.length,0);assert.ok(noWorker.nodes.get('[data-notification-feedback]').textContent.includes('desde su icono'));
 const unsupported=env({permission:'granted',constructorError:true});assert.equal(await unsupported.ui.notify('Test'),false);assert.ok(unsupported.nodes.get('[data-notification-feedback]').textContent.includes('Constructor unsupported'));
 console.log('Notifications: HTTPS, iOS installation, permissions, worker delivery, failures and safe destinations verified');
})().catch(error=>{console.error(error);process.exitCode=1});
