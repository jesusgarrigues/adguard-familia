const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const item={id:9,kind:'blocked',client:'TV',service:'youtube',created:Date.now()/1000,read_at:null,detail:{},target:{kind:'client',client:'TV',service:'youtube',alert_id:9}};
let account={id:1},accepted=false,delivered=0,claimed=false,done=false,push=false,unread=1,requests=0;
const calls=[],counts=[];
const ctx=vm.createContext({window:{ParentalNotifications:{attach(){},update(){},state:()=>({enabled:true}),notify:async()=>{delivered++;return accepted;}},ParentalUI:{setAlerts:n=>counts.push(n),setRequests(){requests++;}}},navigator:{},document:{querySelectorAll:()=>[],addEventListener(){}},crypto:{randomUUID:()=> 'device-1234567890123456'},localStorage:{getItem:()=>null,setItem(){}},setInterval(){},console,Date,Map,Number});
vm.runInContext(fs.readFileSync('assets/notification-center.js','utf8'),ctx);
const api=async(path,body)=>{calls.push({path,body});if(path==='me/alerts/device')return {push};if(path==='me/alerts/read'){unread=0;return {ok:true};}if(path==='me/alerts/result'){if(body.status==='claim'){if(claimed)return {claimed:false};claimed=true;return {claimed:true};}claimed=false;done=body.status==='accepted';return {ok:true};}return {items:[item],unread,requests:[],diagnostic:{push},deliveries:done?[]:[item]};};
const center=ctx.window.ParentalAlertCenter;center.init({account:()=>account,request:api,name:s=>s,navigate(){}});
(async()=>{
 await center.poll();assert.equal(delivered,1);assert.equal(calls.at(-1).body.status,'failed');assert.equal(counts.at(-1),1);
 accepted=true;await center.poll();assert.equal(delivered,2);assert.equal(calls.at(-1).body.status,'accepted');
 await center.poll();assert.equal(delivered,2);assert.equal(requests,3);
 await center.readTarget({alert_id:9});assert.equal(counts.at(-1),0);
 push=true;done=false;await center.poll();assert.equal(delivered,2,'No duplicate foreground notification for a Push device');
 account=null;await center.poll();assert.equal(counts.at(-1),0);
 console.log('Automatic pipeline: first event, failed delivery retry, successful acknowledgement, independent polling, read badge and Push dedup verified');
})().catch(e=>{console.error(e);process.exitCode=1});
