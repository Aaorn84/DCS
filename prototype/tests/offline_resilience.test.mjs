import {CORE_VERSION,CORE_DATASET} from '../shared/core/protocol.ts';
import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {clientOnDisk,hash} from './fixtures/offline_disk_worker.mjs';
import {CheckpointStore} from '../apps/mobile/src/checkpointStore.ts';
import {OfflineRound} from '../apps/mobile/src/offlineRound.ts';
import {createLocalRound,applyLocalCommand,localTotals} from '../shared/core/roundEngine.ts';
const pack={schema:1,local_rules_version:1,dataset:CORE_DATASET,local_command_semantics:2,core_version:CORE_VERSION,round:{id:'r',tee:'蓝Tee',start_hole:1},course:{course_id:'c',holes:Array.from({length:18},(_,i)=>({number:i+1,par:4}))}};
async function prepare(client){
 const raw=JSON.stringify(pack),sha=await hash(raw);
 globalThis.fetch=async()=>new Response(JSON.stringify({offline:{lease_id:'l',round_id:'r',device_id:'device-one',sha256:sha,base_version:0,cursor:0,status:'active'},offline_package:{package:pack,payload_json:raw,sha256:sha}}),{status:200});
 await client.prepare(0);await client.turn('开始球局','start','2026-01-01T00:00:00Z');
}
test('SIGKILL during each checkpoint write restores complete state with idempotent retry',async()=>{
 const previous=globalThis.fetch;
 try{
  for(const crash of ['slot-before','slot-partial','slot-after','head-before','head-after']){
   const directory=mkdtempSync(path.join(tmpdir(),'caddie-kill-'));
   try{
    await prepare(clientOnDisk(directory));
    const child=spawnSync(process.execPath,['--experimental-transform-types',fileURLToPath(new URL('./fixtures/offline_disk_worker.mjs',import.meta.url)),directory,crash],{encoding:'utf8',timeout:10000});
    assert.equal(child.signal,'SIGKILL',crash+': '+child.stderr);globalThis.fetch=async()=>{throw Error('airplane mode');};
    const restarted=clientOnDisk(directory),restored=await restarted.verifyCached();assert.equal(restored.local_state.revision,crash==='head-after'?2:1,crash);
    await restarted.turn('7号铁','selected-club','2026-01-01T00:00:01Z');const saved=await clientOnDisk(directory).verifyCached();assert.equal(saved.local_state.revision,2);assert.equal(saved.queue.length,2);assert.equal(saved.queue[1].event.event_id,'selected-club');
   }finally{rmSync(directory,{recursive:true,force:true});}
  }
 }finally{globalThis.fetch=previous;}
});
test('an 18-hole round stays usable through network loss, repeated cold starts and low storage',async()=>{
 const previous=globalThis.fetch,rows=new Map();let limit=Infinity,networkCalls=0;
 const bytes=()=>[...rows.values()].reduce((n,s)=>n+Buffer.byteLength(s),0);
 const rawStore={getItem:async key=>rows.get(key)??null,setItem:async(key,value)=>{if(bytes()-Buffer.byteLength(rows.get(key)??'')+Buffer.byteLength(value)>limit)throw Error('storage full');rows.set(key,value);},removeItem:async key=>{rows.delete(key);}};
 const make=()=>new OfflineRound('https://offline.invalid','token',new CheckpointStore(rawStore,hash,key=>key==='a'),'a',()=> 'device-one',hash);
 try{
  let client=make();await prepare(client);globalThis.fetch=async()=>{networkCalls++;throw Error('airplane mode');};let id=0;
  const turn=text=>client.turn(text,'c'+(++id),'2026-01-01T00:00:02Z');
  for(let hole=1;hole<=18;hole++){
   await turn('7号铁');await turn('记录已击球');await turn('这洞五杆两推');await turn('确认记录');
   if(hole===9){
    await assert.rejects(client.synchronize(),/无法连接/);const before=await client.cached();limit=bytes();
    await assert.rejects(turn('下一洞'),/存储空间不足/);const restored=await make().verifyCached();assert.equal(restored.local_state.hole,9);assert.deepEqual(restored.queue,before.queue);
    limit=Infinity;
   }
   client=make();await client.verifyCached();if(hole<18)await turn('下一洞');
  }
  await turn('结束球局');const done=await turn('确认结束');assert.deepEqual(done.totals,{holes:18,total:90,putts:36,penalties:0});assert.equal(networkCalls,1);assert.equal(rows.size,5);assert.ok(bytes()<3*1024*1024,'two bounded checkpoints plus one immutable package');
  const final=await make().verifyCached();assert.equal(final.local_state.finished,true);assert.equal(final.local_state.revision,done.local_state.revision);
  // Reconnect: lose the first batch receipt after server commit, then restart and reconcile.
  let remote=createLocalRound(pack),cursor=0,loseReceipt=true;const sha=await hash(JSON.stringify(pack));
  const summary=()=>({revision:remote.revision,hole:remote.hole,stage:remote.stage,totals:localTotals(remote),pending:remote.pending?.phase??null,draft:Boolean(remote.draft)});
  globalThis.fetch=async(_url,init)=>{
   const body=JSON.parse(init.body),accepted=[];
   if(body.action==='offline_sync'){
    for(const entry of body.events){remote=applyLocalCommand(remote,entry.event.data);cursor=entry.seq;accepted.push({seq:entry.seq,event_id:entry.event.event_id,version:entry.seq});}
    if(loseReceipt){loseReceipt=false;throw Error('response lost after server commit');}
   }else assert.equal(body.action,'offline_status');
   return new Response(JSON.stringify({offline:{lease_id:'l',round_id:'r',device_id:'device-one',sha256:sha,base_version:0,cursor,status:'active'},local_status:summary(),accepted}),{status:200});
  };
  await assert.rejects(client.synchronize(),/无法连接/);assert.ok((await make().verifyCached()).queue.length>0);
  client=make();await client.synchronize();const synced=await make().verifyCached();assert.equal(synced.queue.length,0);assert.deepEqual(localTotals(remote),done.totals);assert.equal(remote.finished,true);assert.equal(synced.local_state.revision,remote.revision);

 }finally{globalThis.fetch=previous;}
});

test('a cold start can recover a preparation intent before any package or network response exists',async()=>{
 const {readOfflineSession}=await import('../apps/mobile/src/offlineRecovery.ts');
 const {JourneyClient}=await import('../apps/mobile/src/journey.ts');
 const {JourneyPersistence}=await import('../apps/mobile/src/journeyPersistence.ts');
 const rows=new Map(),previous=globalThis.fetch;
 const raw={getItem:async key=>rows.get(key)??null,setItem:async(key,value)=>{rows.set(key,value);},removeItem:async key=>{rows.delete(key);}};
 const store=new CheckpointStore(raw,hash,()=>true);
 try{
  await new JourneyPersistence(store,'journey').write({schema:1,snapshot:{journey:{version:0,stage:'ready',offline_protocol:2}}});
  globalThis.fetch=async()=>{throw Error('network disabled');};
  const local=new OfflineRound('https://offline.invalid','token',store,'a',()=> 'device-one',hash);
  await assert.rejects(local.prepare(0));
  const restarted=new OfflineRound('https://offline.invalid','token',new CheckpointStore(raw,hash,()=>true),'a',()=> 'unused',hash);
  const restored=await readOfflineSession(restarted,new JourneyClient('https://offline.invalid','token',new JourneyPersistence(store,'journey')));
  assert.equal(restored.preparing,true);assert.equal(restored.disk.package,undefined);assert.equal(restored.disk.local_state,undefined);assert.equal(restored.snapshot.journey.stage,'ready');
 }finally{globalThis.fetch=previous;}
});

test('a large 18-hole ledger stays bounded and recoverable without any network',async()=>{
 const previous=globalThis.fetch,rows=new Map();
 const raw={getItem:async key=>rows.get(key)??null,setItem:async(key,value)=>{rows.set(key,value);},removeItem:async key=>{rows.delete(key);}};
 const make=()=>new OfflineRound('https://offline.invalid','token',new CheckpointStore(raw,hash,key=>key==='a'),'a',()=> 'device-one',hash);
 try{
  let client=make();await prepare(client);globalThis.fetch=async()=>{throw Error('network disabled');};let n=0;
  const command=(name,data={})=>client.execute(name,data,'large'+(++n),'2026-01-01T00:00:02Z');
  for(let hole=1;hole<=18;hole++){
   for(let shot=0;shot<8;shot++){
    await command('select_club',{club:'7号铁'});await command('record_stroke',{is_putt:false});
    await command('set_landing',{point:{latitude:31+hole/1000,longitude:121+shot/10000,accuracy_m:3},lie:shot===7?'green':'fairway'});
   }
   await command('draft_score',{total:10,putts:2,penalties:0});await command('confirm_score',{confirmed:true});
   if(hole===9||hole===18){client=make();await client.verifyCached();}
   if(hole<18)await command('switch_hole',{hole:hole+1});
  }
  const disk=await make().verifyCached();assert.deepEqual(localTotals(disk.local_state),{holes:18,total:180,putts:36,penalties:0});assert.ok(disk.queue.length>480);assert.equal(rows.size,5);
  const head=JSON.parse(rows.get('a.checkpoint.head'));assert.ok(Buffer.byteLength(rows.get('a.checkpoint.'+head.slot))<1024*1024);assert.equal(disk.local_state.undo.length,20);
 }finally{globalThis.fetch=previous;}
});
