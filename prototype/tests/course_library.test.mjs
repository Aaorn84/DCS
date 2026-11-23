import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,randomUUID} from 'node:crypto';
import {CourseLibrary} from '../apps/mobile/src/courseLibrary.ts';
import {OfflineRound} from '../apps/mobile/src/offlineRound.ts';
import {setupAnswer} from '../apps/mobile/src/localSetup.ts';
import {CORE_VERSION,CORE_DATASET} from '../shared/core/protocol.ts';
import {canonicalJson,assembleOfflinePackage} from '../shared/core/offlineSetup.ts';
const sha=async s=>createHash('sha256').update(s).digest('hex');
async function fixture(){
 const rows=new Map(),writes=[];const store={getItem:async k=>rows.get(k)??null,setItem:async(k,v)=>{writes.push(k);rows.set(k,v)},removeItem:async k=>rows.delete(k)};
 const asset={schema:1,core_version:CORE_VERSION,dataset:CORE_DATASET,tees:['蓝Tee'],course:{course_id:'course',map_version:'v1',crs:'WGS84',holes:Array.from({length:18},(_,i)=>({number:i+1,par:4,objects:[]}))}};
 const raw=canonicalJson(asset),digest=await sha(raw),context=canonicalJson({asset_sha256:digest,profile:{},dispersion:{},history_by_hole:{}});
 let reply={asset:{package:asset,payload_json:raw,sha256:digest},context:{payload_json:context,sha256:await sha(context)}};let calls=0;
 const fetcher=async(_url,init)=>{calls++;return new Response(JSON.stringify(init.method==='GET'?{courses:[{course_id:'course',name:'球场',tees:['蓝Tee'],holes:18}]}:reply),{status:200})};
 const library=new CourseLibrary('https://library.test','a',store,'account-a.library',randomUUID,sha);
 return {rows,writes,store,asset,library,fetcher,get calls(){return calls},set reply(value){reply=value},get reply(){return reply}};
}
async function ready(f){await f.library.catalog();await f.library.download('course','蓝Tee');await f.library.saveDraft({memory_allowed:true,patch:{carries:{'7号铁':{low:160,high:160}}},stage:'ready',course_id:'course',tee:'蓝Tee',start_hole:10});}
test('advance download supports offline new rounds, first questions and cold restoration',async()=>{
 const previous=globalThis.fetch,f=await fixture();try{
  globalThis.fetch=f.fetcher;await ready(f);const requests=f.calls;
  globalThis.fetch=async()=>{throw Error('network forbidden')};
  const first=await f.library.prepareLocalRound();assert.equal((await f.library.prepareLocalRound()).id,first.id);const local=new OfflineRound('https://library.test','a',f.store,first.key,randomUUID,sha);const disk=await local.beginOffline(await f.library.materialize(first));
  assert.equal(disk.local_state.hole,10);assert.equal(disk.local_state.stage,'playing');assert.equal(disk.native_start.registered,false);assert.equal(disk.queue.length,1);
  const restoredLibrary=new CourseLibrary('https://library.test','a',f.store,'account-a.library',randomUUID,sha);const record=await restoredLibrary.active();assert.equal(record.phase,'preparing');
  const restored=new OfflineRound('https://library.test','a',f.store,record.key,randomUUID,sha);await restored.beginOffline(await restoredLibrary.materialize(record));await restoredLibrary.activate(record.id);assert.equal((await restored.verifyCached()).queue.length,1);assert.equal(f.calls,requests);
  const index=JSON.parse(f.rows.get('account-a.library'));assert.equal(index.rounds[0].spec.package,undefined);assert.equal(index.rounds[0].spec.course,undefined);
 }finally{globalThis.fetch=previous;}
});
test('failed or incomplete updates preserve the last usable downloaded course',async()=>{
 const previous=globalThis.fetch,f=await fixture();try{
  globalThis.fetch=f.fetcher;await ready(f);const original=(await f.library.read()).downloads[0].asset_sha256;
  f.reply={...f.reply,asset:{...f.reply.asset,sha256:'0'.repeat(64)}};await assert.rejects(f.library.download('course','蓝Tee'),/校验失败/);assert.equal((await f.library.read()).downloads[0].asset_sha256,original);
  const bad={...f.asset,course:{...f.asset.course,holes:f.asset.course.holes.slice(0,17)}};const raw=canonicalJson(bad);f.reply={...f.reply,asset:{package:bad,payload_json:raw,sha256:await sha(raw)}};
  await assert.rejects(f.library.download('course','蓝Tee'),/18 holes/);assert.equal((await f.library.read()).downloads[0].asset_sha256,original);
  const record=await f.library.prepareLocalRound();assert.equal(record.spec.asset_sha256,original);
 }finally{globalThis.fetch=previous;}
});
test('active rounds keep their map when the download is removed and accounts stay isolated',async()=>{
 const previous=globalThis.fetch,f=await fixture();try{
  globalThis.fetch=f.fetcher;await ready(f);const record=await f.library.prepareLocalRound();const local=new OfflineRound('https://library.test','a',f.store,record.key,randomUUID,sha);
  await local.beginOffline(await f.library.materialize(record));await f.library.activate(record.id);await f.library.remove('course','蓝Tee');assert.equal((await local.verifyCached()).local_state.hole,10);
  await assert.rejects(f.library.prepareLocalRound(),/请先完成/);await assert.rejects(f.library.nextSetup(),/尚未结束/);
  const other=new CourseLibrary('https://library.test','b',f.store,'account-b.library',randomUUID,sha);assert.equal((await other.read()).rounds.length,0);assert.equal((await other.read()).downloads.length,0);
 }finally{globalThis.fetch=previous;}
});
test('offline answers require explicit consent and do not interpret unrelated speech as Carry',()=>{
 const initial={memory_allowed:false,patch:{},stage:'memory',start_hole:1};let d=setupAnswer(initial,'不愿意').draft;assert.equal(d.memory_allowed,false);assert.equal(d.stage,'name');
 d={...initial,stage:'proactive'};assert.equal(setupAnswer(d,'什么意思').draft.stage,'proactive');
 d={...initial,stage:'driver'};assert.deepEqual(setupAnswer(d,'不要用一号木260码').draft.patch,{});
 const answer=setupAnswer(d,'3号木210，5号木200');assert.equal(answer.draft.patch.carries['3号木'].high,210);assert.equal(answer.draft.patch.carries['5号木'].high,200);
});
test('personal preference and completed choices survive offline next round only with consent',async()=>{
 const previous=globalThis.fetch,f=await fixture();try{
  globalThis.fetch=f.fetcher;await ready(f);const record=await f.library.prepareLocalRound();const local=new OfflineRound('https://library.test','a',f.store,record.key,randomUUID,sha);
  await local.beginOffline(await f.library.materialize(record));await f.library.activate(record.id);
  globalThis.fetch=async()=>{throw Error('offline')};
  const at='2026-11-23T00:00:00Z';await local.turn('以后优先保守打法','preference',at);
  await local.execute('select_club',{club:'5号木',strategy_choice:'control'},'select',at);await local.execute('record_stroke',{},'hit',at);
  await local.execute('request_finish',{},'finish',at);await local.execute('confirm_finish',{confirmed:true},'confirm',at);
  const draft=(await f.library.nextSetup()).draft;assert.equal(draft.patch.strategy_preference,'control');assert.equal(draft.patch.strategy_usage.length,1);
  await f.library.saveDraft({...draft,stage:'ready'});const next=await f.library.prepareLocalRound();const data=await f.library.materialize(next);
  assert.equal(data.package.package.profile.strategy_preference.value,'control');assert.equal(data.package.package.profile.strategy_usage[0].round_id,record.id);
  const denied=assembleOfflinePackage(f.asset,{profile:{strategy_usage:draft.patch.strategy_usage}},{memory_allowed:false,patch:draft.patch},next.spec.round);assert.equal(denied.profile.strategy_usage,undefined);
  const revoked=setupAnswer(draft,'关闭跨场记忆').draft;assert.equal(revoked.patch.strategy_usage,undefined);
  const setup=setupAnswer({...draft,memory_allowed:false},'以后优先距离打法');assert.equal(setup.draft.patch.strategy_preference,'distance');
 }finally{globalThis.fetch=previous;}
});
test('confirmed Carry, finder and wedge purpose survive the next offline round with original field clocks',async()=>{
 const previous=globalThis.fetch,f=await fixture();try{
  globalThis.fetch=f.fetcher;await ready(f);const r=await f.library.prepareLocalRound();const local=new OfflineRound('https://library.test','a',f.store,r.key,randomUUID,sha);await local.beginOffline(await f.library.materialize(r));await f.library.activate(r.id);
  const at=new Date().toISOString();await local.execute('set_club_carry',{club:'7号铁',low:175,high:175},'carry-revised',at);await local.execute('set_fairway_finder',{club:'4号铁'},'finder-revised',at);await local.execute('set_club_purpose',{club:'58度杆',use:'沙坑'},'purpose-revised',at);
  const before=(await local.cached()).local_state.profile.field_versions['bag:7号铁'];
  await local.execute('request_finish',{},'finish',at);await local.execute('confirm_finish',{confirmed:true},'confirm',at);const d=await f.library.nextSetup();
  await f.library.saveDraft({...d.draft,stage:'ready'});const next=await f.library.prepareLocalRound();const data=await f.library.materialize(next);const profile=data.package.package.profile;
  assert.equal(profile.bag_overrides['7号铁'].high,175);assert.equal(profile.seven.value.distance,175);assert.equal(profile.fairway_finder.value.club,'4号铁');assert.equal(profile.lofted_wedge_uses.value['58'],'沙坑');assert.deepEqual(profile.field_versions['bag:7号铁'],before);
 }finally{globalThis.fetch=previous;}
});
test('unfinished independent rounds cannot be released even when their upload queue is empty',async()=>{
 const previous=globalThis.fetch,f=await fixture();try{
  globalThis.fetch=f.fetcher;await ready(f);const r=await f.library.prepareLocalRound();const local=new OfflineRound('https://library.test','a',f.store,r.key,randomUUID,sha);await local.beginOffline(await f.library.materialize(r));await f.library.activate(r.id);
  globalThis.fetch=async()=>{throw Error('release must not reach network')};await assert.rejects(local.release(),/请先同步/);
  // Queue-empty is not proof that the round ended; the server guard is tested separately.
  const disk=JSON.parse(f.rows.get(r.key));disk.queue=[];disk.lease.cursor=disk.next-1;f.rows.set(r.key,JSON.stringify(disk));const restored=new OfflineRound('https://library.test','a',f.store,r.key,randomUUID,sha);
  await assert.rejects(restored.release(),/请先确认结束/);assert.equal((await restored.cached()).lease.status,'active');
 }finally{globalThis.fetch=previous;}
});
