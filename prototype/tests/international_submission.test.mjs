import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const script=fs.readFileSync(new URL('../../demo-local/international.html',import.meta.url),'utf8').split('<script>')[1].split('</script>')[0];
function setup(fetcher){
 const nodes=new Map();const get=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:true,disabled:false});return nodes.get(id)};
 let id=0;const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[...nodes.values()]},fetch:fetcher,crypto:{randomUUID:()=>`operation-${++id}`}});
 vm.runInContext(script,context);vm.runInContext("token='test';version=4",context);return {context,get,value:code=>vm.runInContext(code,context)};
}
test('international web retries the original operation after a temporary HTTP failure',async()=>{
 for(const status of [429,500,503]){
  const bodies=[];let attempt=0;const ui=setup(async(_url,init)=>{bodies.push(init.body);const code=attempt++?200:status;return {ok:code===200,status:code,json:async()=>code===200?{configuration:{locale:'zh-CN',distance_unit:'yd'},journey:{stage:'name'},version:5}:{error:'temporary'}}});
  ui.get('utterance').value='确认记录';await ui.get('send').onclick();assert.ok(ui.value('pending'));assert.equal(ui.get('retry').hidden,false);
  await ui.get('retry').onclick();assert.equal(bodies[0],bodies[1]);assert.equal(ui.value('pending'),null);assert.equal(ui.get('retry').hidden,true);
 }
});
test('international web releases a rejected stale request for user review',async()=>{
 const ui=setup(async()=>({ok:false,status:409,json:async()=>({error:'state conflict'})}));await ui.get('send').onclick();assert.equal(ui.value('pending'),null);assert.equal(ui.get('retry').hidden,true);
});
