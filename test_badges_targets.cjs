const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context=vm.createContext({URL,URLSearchParams});vm.runInContext(fs.readFileSync('assets/notification-targets.js','utf8'),context);
const t=context.ParentalTargets;
assert.equal(t.url({kind:'request',id:17}),'/?view=requests#request=17');
assert.equal(t.fromURL('https://parental.test/?view=requests#request=17').id,17);
assert.equal(t.normalize({kind:'request',id:-1}),null);assert.equal(t.normalize({kind:'request',id:'1e9'}),null);
assert.equal(t.normalize({kind:'request',id:Infinity}),null);assert.equal(t.normalize({kind:'external',url:'https://evil.test/'}),null);
const client={kind:'client',client:'iMac de Martín & Emma',service:'youtube'};
assert.equal(t.fromURL('https://parental.test'+t.url(client)).client,client.client);assert.ok(t.url(client).startsWith('/?view=clients#'));
assert.equal(t.normalize({kind:'client',client:'a\n',service:'youtube'}),null);
function badgeEnv(nav){const notes=[];const ctx=vm.createContext({window:{Notification:{permission:'granted'}},navigator:nav,document:{querySelectorAll:()=>[{set textContent(v){notes.push(v)}}]},Promise,Number});vm.runInContext(fs.readFileSync('assets/app-badges.js','utf8'),ctx);return {ui:ctx.window.ParentalBadges,notes};}
(async()=>{
 const calls=[];const {ui}=badgeEnv({setAppBadge:async n=>calls.push(n),clearAppBadge:async()=>calls.push('clear')});
 const first=ui.update(2,{id:1}),second=ui.update(0,null);await Promise.all([first,second]);assert.deepEqual(calls,[2,'clear']);
 await ui.update(1,{id:2});await ui.update(1,{id:2});assert.deepEqual(calls,[2,'clear',1]);
 await ui.update(999,null);assert.equal(calls.at(-1),'clear');
 const absent=badgeEnv({});await absent.ui.update(5,{id:1});assert.equal(absent.ui.supported(),false);assert.ok(absent.ui.status().includes('Android'));
 const rejected=badgeEnv({setAppBadge:async()=>{throw Error('unsupported')},clearAppBadge:async()=>{}});await rejected.ui.update(1,{id:1});assert.ok(rejected.ui.status().includes('no ha permitido'));
 console.log('Badge queue, account clearing, absent/rejected API and internal request/client destinations verified');
})().catch(error=>{console.error(error);process.exitCode=1});
