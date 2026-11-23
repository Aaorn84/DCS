import test from 'node:test';
import assert from 'node:assert/strict';
import {JourneyClient} from '../apps/mobile/src/journey.ts';
test('lost journey receipt retries exactly the original envelope',async()=>{
 const previous=globalThis.fetch, bodies=[];let first=true;
 globalThis.fetch=async(_url,init)=>{bodies.push(init.body);if(first){first=false;throw Error('lost response')}return new Response(JSON.stringify({journey:{stage:'name'}}),{status:200,headers:{'Content-Type':'application/json'}})};
 try{const c=new JourneyClient('http://example.test','test-token');await assert.rejects(c.submit({type:'message',event_id:'e',text:'可以记住'},'op',0));assert.ok(c.pending);await c.retry();assert.equal(bodies[0],bodies[1]);assert.equal(c.pending,null)}finally{globalThis.fetch=previous}
});
test('a server version conflict clears retry rather than resending a stale answer',async()=>{
 const previous=globalThis.fetch;
 globalThis.fetch=async()=>new Response(JSON.stringify({error:'version conflict'}),{status:409,headers:{'Content-Type':'application/json'}});
 try{const c=new JourneyClient('http://example.test','test-token');await assert.rejects(c.submit({type:'message',event_id:'e',text:'阿明'},'op',0));assert.equal(c.pending,null);await assert.rejects(c.retry(),/没有待重试/)}finally{globalThis.fetch=previous}
});
test('pending receipt survives restart and account-scoped persistence stays isolated',async()=>{
 const {JourneyPersistence}=await import('../apps/mobile/src/journeyPersistence.ts');
 const rows=new Map();const store={getItem:async k=>rows.get(k)??null,setItem:async(k,v)=>{rows.set(k,v)}};
 const prior=globalThis.fetch;const bodies=[];
 try{
  globalThis.fetch=async(_u,init)=>{bodies.push(init.body);throw Error('offline')};
  const first=new JourneyClient('http://example.test','token',new JourneyPersistence(store,'account-a'));
  await assert.rejects(first.submit({type:'message',event_id:'event',text:'五杆'},'op',2));
  const restored=new JourneyClient('http://example.test','new-token',new JourneyPersistence(store,'account-a'));await restored.restore();assert.equal(restored.pending.operation_id,'op');
  const other=new JourneyClient('http://example.test','other',new JourneyPersistence(store,'account-b'));await other.restore();assert.equal(other.pending,null);
  globalThis.fetch=async(_u,init)=>{bodies.push(init.body);return new Response(JSON.stringify({journey:{stage:'active',version:3}}),{status:200})};
  await restored.retry();assert.equal(bodies[0],bodies[1]);
  const again=new JourneyClient('http://example.test','token',new JourneyPersistence(store,'account-a'));const cached=await again.cachedSnapshot();assert.equal(cached.journey.version,3);assert.equal(again.pending,null);
 }finally{globalThis.fetch=prior}
});

test('storage failure after a server receipt reloads the durable snapshot and original retry envelope',async()=>{
 const {JourneyPersistence}=await import('../apps/mobile/src/journeyPersistence.ts');const {CheckpointStore}=await import('../apps/mobile/src/checkpointStore.ts');const {createHash}=await import('node:crypto');
 const previous=globalThis.fetch,rows=new Map();let fail=false;
 const raw={getItem:async k=>rows.get(k)??null,setItem:async(k,v)=>{if(fail)throw Error('storage full');rows.set(k,v);},removeItem:async k=>{rows.delete(k);}};
 const store=new CheckpointStore(raw,async s=>createHash('sha256').update(s).digest('hex'),()=>true);
 const c=new JourneyClient('https://example.test','token',new JourneyPersistence(store,'a'));
 try{
  globalThis.fetch=async()=>new Response(JSON.stringify({journey:{version:1}}),{status:200});await c.snapshot();
  globalThis.fetch=async()=>{fail=true;return new Response(JSON.stringify({journey:{version:2}}),{status:200});};
  await assert.rejects(c.submit({type:'message',event_id:'event',text:'六杆'},'op',1),/存储空间不足/);
  const cached=await c.cachedSnapshot();assert.equal(cached.journey.version,1);assert.equal(c.pending.operation_id,'op');
  fail=false;globalThis.fetch=async(_url,init)=>{assert.equal(JSON.parse(init.body).operation_id,'op');return new Response(JSON.stringify({journey:{version:2}}),{status:200});};
  await c.retry();assert.equal(c.pending,null);assert.equal((await c.cachedSnapshot()).journey.version,2);
 }finally{globalThis.fetch=previous;}
});
test('temporary HTTP failures preserve the durable original envelope across restart',async()=>{
 const {JourneyPersistence}=await import('../apps/mobile/src/journeyPersistence.ts');const previous=globalThis.fetch;
 try{
  for(const status of [408,425,429,500,502,503,504]){
   const rows=new Map(),bodies=[];const store={getItem:async k=>rows.get(k)??null,setItem:async(k,v)=>rows.set(k,v)};
   globalThis.fetch=async(_url,init)=>{bodies.push(init.body);return new Response(JSON.stringify({error:'temporary'}),{status})};
   const first=new JourneyClient('https://example.test','token',new JourneyPersistence(store,'a'));
   await assert.rejects(first.submit({type:'message',event_id:'original-event',text:'确认记录'},'original-operation',7));assert.ok(first.pending,status);
   await assert.rejects(first.submit({type:'message'},'new-id',7),/上次请求/);
   const restored=new JourneyClient('https://example.test','token',new JourneyPersistence(store,'a'));await restored.restore();assert.equal(restored.pending.operation_id,'original-operation');
   globalThis.fetch=async(_url,init)=>{bodies.push(init.body);return new Response(JSON.stringify({journey:{version:8}}),{status:200})};
   await restored.retry();assert.equal(bodies[0],bodies[1]);assert.equal(JSON.parse(bodies[1]).expected_version,7);assert.equal(restored.pending,null);
  }
 }finally{globalThis.fetch=previous;}
});
