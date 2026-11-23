import {CORE_VERSION,CORE_DATASET} from '../shared/core/protocol.ts';
import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {OfflineRound} from '../apps/mobile/src/offlineRound.ts';
const hash=async text=>createHash('sha256').update(text).digest('hex');
function fixture(){const rows=new Map();const store={getItem:async k=>rows.get(k)??null,setItem:async(k,v)=>rows.set(k,v)};const make=(key='a')=>new OfflineRound('https://example.test','token',store,key,()=> 'device-one',hash);return {rows,store,make};}
function response(value){return new Response(JSON.stringify(value),{status:200});}
test('current package raw-byte hash survives Python float formatting and queue restarts',async()=>{
 const old=globalThis.fetch,h=await localHarness();let calls=0;
 try{
  globalThis.fetch=async(_u,init)=>{calls++;const result=await h.wire(JSON.parse(init.body));const pack=result.offline_package.package;pack.profile={driver:{value:{distance:260}}};const raw=JSON.stringify(pack).replace('"distance":260','"distance":260.0');const sha=await hash(raw);h.lease.sha256=sha;return response({...result,offline:{...h.lease},offline_package:{package:pack,payload_json:raw,sha256:sha}});};
  await h.client.prepare(0);await h.client.turn('开始球局','e1',new Date().toISOString());assert.equal(calls,1);
  const restart=h.make();assert.equal((await restart.cached()).queue.length,1);assert.equal((await h.make('b').cached()).queue.length,0);await restart.verifyCached();
 }finally{globalThis.fetch=old}
});
test('tampered package is not installed and pending queue blocks release',async()=>{
 const old=globalThis.fetch;const {make}=fixture();
 try{
  globalThis.fetch=async()=>response({offline:{sha256:'wrong'},offline_package:{package:{a:1},payload_json:'{"a":1}',sha256:'wrong'}});
  const client=make();await assert.rejects(client.prepare(0),/校验失败/);assert.equal((await client.cached()).lease,undefined);
 }finally{globalThis.fetch=old}
});
test('typed sequence and payload remain identical on a lost sync reply',async()=>{
 const old=globalThis.fetch,h=await localHarness(),batches=[];
 try{
  globalThis.fetch=async(_u,init)=>response(await h.wire(JSON.parse(init.body)));
  await h.client.prepare(0);await h.client.turn('开始球局','e1',new Date().toISOString());
  globalThis.fetch=async(_u,init)=>{const body=JSON.parse(init.body);if(body.action==='offline_sync'){batches.push(body);if(batches.length===1)throw Error('lost');}return response(await h.wire(body));};
  await assert.rejects(h.client.release(),/先同步/);await assert.rejects(h.client.synchronize());await h.make().synchronize();assert.deepEqual(batches[0],batches[1]);
 }finally{globalThis.fetch=old}
});
test('a complete round is saved with no network calls after preparation, including restart',async()=>{
 const old=globalThis.fetch;const {make}=fixture();const pack={schema:1,local_rules_version:1,dataset:CORE_DATASET,local_command_semantics:2,core_version:CORE_VERSION,round:{id:'r',tee:'蓝Tee',start_hole:1},course:{course_id:'c',holes:Array.from({length:18},(_,i)=>({number:i+1,par:4}))}};const raw=JSON.stringify(pack);const sha=await hash(raw);let calls=0;
 try{
  globalThis.fetch=async(_u,init)=>{calls++;assert.equal(JSON.parse(init.body).local_engine_version,1);return response({offline:{lease_id:'l',round_id:'r',device_id:'device-one',sha256:sha,base_version:0,cursor:0,status:'active'},offline_package:{package:pack,payload_json:raw,sha256:sha}})};
  let client=make();await client.prepare(0);globalThis.fetch=async()=>{throw Error('no network in airplane-mode simulation')};let id=0;
  const turn=async text=>client.turn(text,'cmd'+(++id),new Date().toISOString());await turn('开始球局');
  for(let hole=1;hole<=18;hole++){
   await turn('7号铁');await turn('记录已击球');const draft=await turn('这洞三杆两推');assert.match(draft.text,/确认/);await turn('确认记录');
   if(hole===9){client=make();assert.equal((await client.verifyCached()).local_state.hole,9);}
   if(hole<18)await turn('下一洞');
  }
  await turn('结束球局');const ended=await turn('确认结束');assert.deepEqual(ended.totals,{holes:18,total:54,putts:36,penalties:0});assert.equal(ended.local_state.finished,true);assert.equal(calls,1);assert.ok((await client.cached()).queue.length>70);
 }finally{globalThis.fetch=old}
});
test('local state and event are not acknowledged if durable storage fails',async()=>{
 const old=globalThis.fetch;const f=fixture();let fail=false;const store={getItem:f.store.getItem,setItem:async(k,v)=>{if(fail)throw Error('disk full');return f.store.setItem(k,v)}};const client=new OfflineRound('https://example.test','token',store,'a',()=> 'device-one',hash);const pack={schema:1,local_rules_version:1,dataset:CORE_DATASET,local_command_semantics:2,core_version:CORE_VERSION,round:{id:'r',tee:'蓝Tee'},course:{course_id:'c',holes:Array.from({length:18},(_,i)=>({number:i+1,par:4}))}};const raw=JSON.stringify(pack),sha=await hash(raw);
 try{
  globalThis.fetch=async()=>response({offline:{lease_id:'l',round_id:'r',device_id:'device-one',sha256:sha,base_version:0,cursor:0,status:'active'},offline_package:{package:pack,payload_json:raw,sha256:sha}});await client.prepare(0);fail=true;
  await assert.rejects(client.turn('开始球局','cmd1',new Date().toISOString()),/disk full/);fail=false;const disk=await client.cached();assert.equal(disk.local_state.revision,0);assert.equal(disk.queue.length,0);
 }finally{globalThis.fetch=old}
});
test('immutable map package is not serialized or written again for each local utterance',async()=>{
 const old=globalThis.fetch;const f=fixture(),writes=[];const store={getItem:f.store.getItem,setItem:async(k,v)=>{writes.push([k,v.length]);return f.store.setItem(k,v)}};const client=new OfflineRound('https://example.test','token',store,'a',()=> 'device-one',hash);
 const pack={schema:1,local_rules_version:1,dataset:CORE_DATASET,local_command_semantics:2,core_version:CORE_VERSION,round:{id:'r',tee:'蓝Tee'},course:{course_id:'c',geometry:'x'.repeat(100000),holes:Array.from({length:18},(_,i)=>({number:i+1,par:4}))}};const raw=JSON.stringify(pack),sha=await hash(raw);
 try{
  globalThis.fetch=async()=>response({offline:{lease_id:'l',round_id:'r',device_id:'device-one',sha256:sha,base_version:0,cursor:0,status:'active'},offline_package:{package:pack,payload_json:raw,sha256:sha}});await client.prepare(0);const n=writes.filter(([key])=>key.includes('.package.')).length;
  await client.turn('开始球局','c1',new Date().toISOString());await client.turn('7号铁','c2',new Date().toISOString());assert.equal(writes.filter(([key])=>key.includes('.package.')).length,n);assert.ok(writes.at(-1)[1]<10000);
  const restart=new OfflineRound('https://example.test','token',store,'a',()=> 'unused-id',hash);assert.equal((await restart.cached()).package.package.course.geometry.length,100000);
 }finally{globalThis.fetch=old}
});
test('cold restoration verifies the saved state against its event history',async()=>{
 const old=globalThis.fetch;const f=fixture();const pack={schema:1,local_rules_version:1,dataset:CORE_DATASET,local_command_semantics:2,core_version:CORE_VERSION,round:{id:'r',tee:'蓝Tee'},course:{course_id:'c',holes:Array.from({length:18},(_,i)=>({number:i+1,par:4}))}};const raw=JSON.stringify(pack),sha=await hash(raw);
 try{
  globalThis.fetch=async()=>response({offline:{lease_id:'l',round_id:'r',device_id:'device-one',sha256:sha,base_version:0,cursor:0,status:'active'},offline_package:{package:pack,payload_json:raw,sha256:sha}});const client=f.make();await client.prepare(0);await client.turn('开始球局','c1',new Date().toISOString());await f.make().verifyCached();
  const damaged=JSON.parse(f.rows.get('a'));damaged.local_state.state.holes['1'].score={total:1,putts:0,penalties:0};f.rows.set('a',JSON.stringify(damaged));await assert.rejects(f.make().verifyCached(),/无法由已保存事件重建/);
 }finally{globalThis.fetch=old}
});

async function localHarness(storeOverride){
 const {createLocalRound,applyLocalCommand,localTotals}=await import('../shared/core/roundEngine.ts');
 const f=fixture();const store=storeOverride?storeOverride(f.store):f.store;
 const client=new OfflineRound('https://example.test','token',store,'a',()=> 'device-one',hash);
 const pack={schema:1,local_rules_version:1,dataset:CORE_DATASET,local_command_semantics:2,core_version:CORE_VERSION,round:{id:'r',tee:'蓝Tee'},course:{course_id:'c',holes:Array.from({length:18},(_,i)=>({number:i+1,par:4}))}};
 const raw=JSON.stringify(pack),sha=await hash(raw);let model=createLocalRound(pack);const lease={lease_id:'lease',round_id:'r',device_id:'device-one',sha256:sha,base_version:0,cursor:0,status:'active'};
 const summary=()=>({revision:model.revision,hole:model.hole,stage:model.stage,totals:localTotals(model),pending:model.pending?.phase??null,draft:Boolean(model.draft)});
 const wire=async body=>{
  if(body.action==='offline_prepare')return {offline:{...lease},offline_package:{package:pack,payload_json:raw,sha256:sha}};
  if(body.action==='offline_activate'){lease.status='active';return {offline:{...lease}};}
  if(body.action==='offline_cancel_preparation'){lease.status='cancelled';return {offline:{...lease}};}
  if(body.action==='offline_status')return {offline:{...lease},local_status:summary()};
  if(body.action==='offline_sync'){const accepted=[];for(const e of body.events){model=applyLocalCommand(model,e.event.data);lease.cursor=e.seq;accepted.push({seq:e.seq,event_id:e.event.event_id,version:e.seq});}return {offline:{...lease},accepted,local_status:summary()};}
  throw Error('unexpected action '+body.action);
 };
 return {...f,client,wire,lease};
}
test('a slow background sync does not lock local voice commands or lose new appended entries',async()=>{
 const previous=globalThis.fetch;const h=await localHarness();let unlock,entered;const waiting=new Promise(r=>entered=r),gate=new Promise(r=>unlock=r);
 try{
  globalThis.fetch=async(_u,init)=>response(await h.wire(JSON.parse(init.body)));await h.client.prepare(0);await h.client.turn('开始球局','c1',new Date().toISOString());
  globalThis.fetch=async(_u,init)=>{const body=JSON.parse(init.body);if(body.action==='offline_status'){entered();await gate;}return response(await h.wire(body));};
  const sync=h.client.synchronize();await waiting;const local=await h.client.turn('7号铁','c2',new Date().toISOString());assert.equal(local.local_state.revision,2);unlock();await sync;
  const disk=await h.client.cached();assert.equal(disk.local_state.revision,2);assert.equal(disk.queue.length,0);assert.equal(disk.lease.cursor,2);
 }finally{globalThis.fetch=previous}
});
test('missing or malformed acknowledgements never remove queued events',async()=>{
 const previous=globalThis.fetch;
 try{
  for(const corrupt of [r=>{delete r.local_status},r=>{r.offline.device_id='wrong-device'},r=>{r.offline.cursor=99},r=>{r.accepted[0].event_id='wrong-event'},r=>{r.local_status.totals.total=99}]){
   const h=await localHarness();globalThis.fetch=async(_u,init)=>response(await h.wire(JSON.parse(init.body)));await h.client.prepare(0);await h.client.turn('开始球局','c1',new Date().toISOString());
   globalThis.fetch=async(_u,init)=>{const b=JSON.parse(init.body),r=await h.wire(b);if(b.action==='offline_sync')corrupt(r);return response(r);};await assert.rejects(h.client.synchronize());
   assert.equal((await h.client.cached()).queue.length,1);assert.equal((await h.client.cached()).lease.cursor,0);
   globalThis.fetch=async(_u,init)=>response(await h.wire(JSON.parse(init.body)));await h.client.synchronize();assert.equal((await h.client.cached()).queue.length,0);
  }
 }finally{globalThis.fetch=previous}
});
test('failed local preparation never activates the reservation and can be cancelled',async()=>{
 const previous=globalThis.fetch;let fail=true,activations=0;
 const h=await localHarness(store=>({...store,setItem:async(k,v)=>{if(fail&&k==='a'&&JSON.parse(v).lease?.status==='preparing')throw Error('disk full');return store.setItem(k,v)}}));h.lease.status='preparing';
 try{
  globalThis.fetch=async(_u,init)=>{const b=JSON.parse(init.body);if(b.action==='offline_activate')activations++;return response(await h.wire(b));};await assert.rejects(h.client.prepare(0),/disk full/);assert.equal(activations,0);assert.equal(h.lease.status,'preparing');assert.ok((await h.client.cached()).prepare_intent);
  fail=false;await h.client.cancelPreparation();assert.equal(h.lease.status,'cancelled');assert.equal((await h.client.cached()).local_state,undefined);
 }finally{globalThis.fetch=previous}
});
test('a lost activation response can recover the same preparation without a new lease',async()=>{
 const previous=globalThis.fetch;const h=await localHarness();h.lease.status='preparing';let lost=true;
 try{
  globalThis.fetch=async(_u,init)=>{const b=JSON.parse(init.body),r=await h.wire(b);if(b.action==='offline_activate'&&lost){lost=false;throw Error('lost activation response')}return response(r);};
  await assert.rejects(h.client.prepare(0));assert.equal((await h.client.cached()).lease.status,'preparing');assert.equal(h.lease.status,'active');const recovered=await h.client.recoverPreparation();assert.equal(recovered.lease.status,'active');assert.equal(recovered.prepare_intent,undefined);
 }finally{globalThis.fetch=previous}
});
test('clock rollback preserves order by sequence while retaining original device timestamps',async()=>{
 const previous=globalThis.fetch;const h=await localHarness();
 try{
  globalThis.fetch=async(_u,init)=>response(await h.wire(JSON.parse(init.body)));await h.client.prepare(0);const at=new Date().toISOString(),older=new Date(Date.now()-3600000).toISOString();await h.client.turn('开始球局','c1',at);const result=await h.client.turn('7号铁','c2',older);assert.equal(result.clock_warning,true);assert.equal((await h.client.cached()).queue[1].event.observed_at,older);await h.client.synchronize();assert.equal((await h.client.cached()).lease.cursor,2);
 }finally{globalThis.fetch=previous}
});
test('cancelling an in-flight sync prevents late replies from overwriting new local state',async()=>{
 const previous=globalThis.fetch;const h=await localHarness();let unlock,entered;const waiting=new Promise(r=>entered=r),gate=new Promise(r=>unlock=r);
 try{
  globalThis.fetch=async(_u,init)=>response(await h.wire(JSON.parse(init.body)));await h.client.prepare(0);await h.client.turn('开始球局','c1',new Date().toISOString());
  globalThis.fetch=async(_u,init)=>{const b=JSON.parse(init.body);if(b.action==='offline_status'){entered();await gate;}return response(await h.wire(b));};const sync=h.client.synchronize();await waiting;await h.client.cancelSynchronization();await h.client.turn('7号铁','c2',new Date().toISOString());unlock();await assert.rejects(sync,/已取消/);assert.equal((await h.client.cached()).queue.length,2);assert.equal((await h.client.cached()).local_state.revision,2);
 }finally{globalThis.fetch=previous}
});
test('storage capacity guard retains the previous saved round instead of acknowledging oversized data',async()=>{
 const previous=globalThis.fetch;const h=await localHarness();
 try{
  globalThis.fetch=async(_u,init)=>response(await h.wire(JSON.parse(init.body)));await h.client.prepare(0);await h.client.turn('开始球局','c1',new Date().toISOString());await assert.rejects(h.client.execute('select_club',{club:'7号铁',extra:'x'.repeat(1100000)},'c2',new Date().toISOString()),/容量上限/);const disk=await h.client.cached();assert.equal(disk.local_state.revision,1);assert.equal(disk.queue.length,1);
 }finally{globalThis.fetch=previous}
});

test('concurrent cold reads initialize and persist the device identity only once',async()=>{
 const rows=new Map();let ids=0,writes=0,open;const gate=new Promise(resolve=>open=resolve);
 const store={getItem:async key=>{await gate;return rows.get(key)??null;},setItem:async(key,value)=>{writes++;rows.set(key,value);}};
 const client=new OfflineRound('https://example.test','token',store,'a',()=> 'device-'+(++ids),hash);
 const first=client.cached(),second=client.cached();open();const [a,b]=await Promise.all([first,second]);
 assert.equal(ids,1);assert.equal(writes,1);assert.equal(a.device_id,b.device_id);assert.equal(JSON.parse(rows.get('a')).device_id,a.device_id);
});
test('failed initialization is retried instead of exposing an unpersisted device identity',async()=>{
 const f=fixture();let fail=true,ids=0;
 const store={...f.store,setItem:async(k,v)=>{if(fail)throw Error('disk full');return f.store.setItem(k,v);}};
 const client=new OfflineRound('https://example.test','token',store,'a',()=> 'device-'+(++ids),hash);
 await assert.rejects(client.cached(),/disk full/);fail=false;const saved=await client.cached();assert.equal(saved.device_id,'device-2');assert.equal(JSON.parse(f.rows.get('a')).device_id,saved.device_id);
});
test('failed cancellation or release reloads the last durable lease and can retry',async()=>{
 const previous=globalThis.fetch;
 try{
  for(const action of ['offline_cancel_preparation','offline_release']){
   let fail=false;const h=await localHarness(store=>({...store,setItem:async(k,v)=>{if(fail&&k==='a')throw Error('disk full');return store.setItem(k,v);}}));
   globalThis.fetch=async(_u,init)=>{const body=JSON.parse(init.body);if(body.action==='offline_release'){h.lease.status='released';return response({offline:{...h.lease}});}return response(await h.wire(body));};
   await h.client.prepare(0);const operation=()=>action==='offline_release'?h.client.release():h.client.cancelPreparation();
   fail=true;await assert.rejects(operation(),/disk full/);assert.equal((await h.client.cached()).lease.status,'active');assert.ok((await h.client.cached()).local_state);
   fail=false;await operation();const saved=await h.client.cached();assert.equal(saved.lease?.status,action==='offline_release'?'released':undefined);
  }
 }finally{globalThis.fetch=previous}
});
test('failed package replacement does not publish the new package from memory',async()=>{
 const previous=globalThis.fetch;const f=fixture();let fail=false;
 const store={...f.store,setItem:async(k,v)=>{if(fail&&k==='a')throw Error('disk full');return f.store.setItem(k,v);}};
 const client=new OfflineRound('https://example.test','token',store,'a',()=> 'device-one',hash);
 try{
  let pack={core_version:CORE_VERSION,dataset:CORE_DATASET,local_command_semantics:2,local_rules_version:1,course:'first'};globalThis.fetch=async()=>{const raw=JSON.stringify(pack);return response({package:pack,payload_json:raw,sha256:await hash(raw)});};
  await client.download();pack={...pack,course:'second'};fail=true;await assert.rejects(client.download(),/disk full/);assert.equal((await client.cached()).package.package.course,'first');
  fail=false;await client.download();assert.equal((await client.cached()).package.package.course,'second');
 }finally{globalThis.fetch=previous}
});
test('unversioned packages and embedded prior disk packages cannot be adopted',async()=>{
 const previous=globalThis.fetch,h=await localHarness();
 try{
  globalThis.fetch=async(_u,init)=>{const result=await h.wire(JSON.parse(init.body));delete result.offline_package.package.core_version;const raw=JSON.stringify(result.offline_package.package);const sha=await hash(raw);result.offline.sha256=sha;result.offline_package={package:result.offline_package.package,payload_json:raw,sha256:sha};return response(result);};
  await assert.rejects(h.client.prepare(0),/核心版本不匹配/);assert.equal((await h.client.cached()).lease,undefined);
  h.rows.set('a',JSON.stringify({schema:1,device_id:'device-one',package:{package:{course:'old'}},queue:[],next:1}));await assert.rejects(h.make().cached(),/旧内嵌地图存储/);
  assert.equal(typeof OfflineRound.prototype.enqueue,'undefined');
 }finally{globalThis.fetch=previous}
});
