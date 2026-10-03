const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const elements=new Map();const get=id=>{if(!elements.has(id))elements.set(id,{value:'',textContent:'',hidden:false,addEventListener(){}});return elements.get(id)};
const context=vm.createContext({console,sessionStorage:{getItem:()=>null,setItem(){}},document:{getElementById:get,querySelectorAll:()=>[],createElement:()=>({})},window:{addEventListener(){}},setInterval:()=>0});
const code=fs.readFileSync('index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];vm.runInContext(code,context);
(async()=>{
await vm.runInContext(`(async()=>{token='test';page='server';state=null;dirty=true;let calls=0,renders=0;request=async()=>{calls++;throw Object.assign(Error('Timeout'),{status:502})};render=()=>{renders++};await refresh();if(calls!==0)throw Error('Background polling must not touch server form');await refresh(true);if(renders!==0)throw Error('Network failure recreated server form');if(!dirty)throw Error('Network failure lost dirty state');page='client';await refresh();if(calls!==1)throw Error('Dirty client form must pause polling')})()`,context);
console.log('UI regression: server form preserved after failures; background polling paused for server and dirty forms');
})().catch(e=>{console.error(e);process.exitCode=1});
