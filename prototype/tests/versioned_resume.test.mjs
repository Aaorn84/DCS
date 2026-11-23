import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash,randomUUID} from 'node:crypto';
import fs from 'node:fs';
import {coreFor,coreForPackage,SUPPORTED_CORES} from '../shared/core/runtime.ts';
import {CORE_VERSION} from '../shared/core/protocol.ts';
import {OfflineRound} from '../apps/mobile/src/offlineRound.ts';
import {savePackage} from '../apps/mobile/src/immutablePackage.ts';
const hash=async s=>createHash('sha256').update(s).digest('hex');
import {oldCheckpoint} from './fixtures/old_checkpoint.mjs';
test('old ninth-hole checkpoint resumes offline under bundled original core and new games use current core',async()=>{
 const previous=globalThis.fetch;let requests=0;try{globalThis.fetch=async()=>{requests++;throw Error('offline')};const f=await oldCheckpoint();const local=new OfflineRound('https://offline.test','a',f.store,f.key,randomUUID,hash);
  assert.equal((await local.verifyCached()).local_state.core_version,'1.4.0');await local.turn('7号铁','after-upgrade',new Date().toISOString());let d=await local.cached();assert.equal(d.local_state.selection.strategy_choice,undefined);
  await assert.rejects(local.execute('set_strategy_preference',{preference:'control'},'new-command',new Date().toISOString()),/unsupported local command/);
  const advice=await local.strategy();assert.equal(advice.core_version,'1.4.0');assert.equal(advice.policy_version,undefined);
  await local.execute('record_stroke',{},'stroke-after-upgrade',new Date().toISOString());assert.equal((await local.verifyCached()).local_state.holes['10'].rows[0].club,'7号铁');assert.equal(requests,0);
  const next={...f.envelope.package,core_version:CORE_VERSION};assert.equal(coreForPackage(next).createLocalRound(next).core_version,CORE_VERSION);
 }finally{globalThis.fetch=previous;}
});
test('unknown versions fail closed without deleting records or relabelling the package',async()=>{
 const f=await oldCheckpoint();const before=[...f.rawRows];assert.throws(()=>coreFor('9.9.9'),/version mismatch/);assert.deepEqual([...f.rawRows],before);
 assert.throws(()=>coreForPackage({...f.envelope.package,dataset:'other-dataset'}),/incompatible/);
 const unknown={...f.envelope.package,core_version:'9.9.9'},payload_json=JSON.stringify(unknown),digest=await hash(payload_json);
 await savePackage(f.store,f.key+'.package.'+digest,{package:unknown,payload_json,sha256:digest,source_version:0});
 await f.store.setItem(f.key,JSON.stringify({...f.disk,package_ref:digest}));const saved=[...f.rawRows];
 const local=new OfflineRound('https://offline.test','a',f.store,f.key,randomUUID,hash);await assert.rejects(local.verifyCached(),/version mismatch/);assert.deepEqual([...f.rawRows],saved);
});
test('frozen old release has a verified complete local dependency closure',()=>{
 const root=new URL('../shared/core/releases/1.4.0/',import.meta.url);const manifest=JSON.parse(fs.readFileSync(new URL('manifest.json',root),'utf8'));
 for(const [file,digest] of Object.entries(manifest.files)){
  const bytes=fs.readFileSync(new URL(file,root));assert.equal(createHash('sha256').update(bytes).digest('hex'),digest,file);
  for(const match of bytes.toString().matchAll(/from ['"](.+?)['"]/g)){assert.ok(match[1].startsWith('./'));assert.ok(manifest.files[match[1].slice(2)],match[1]);}
 }
 assert.ok(SUPPORTED_CORES.includes(manifest.core_version));
});
test('interrupted old offline start can still materialize its original package after upgrading',async()=>{
 const {CourseLibrary}=await import('../apps/mobile/src/courseLibrary.ts');const f=await oldCheckpoint();
 const assetRaw=coreFor('1.4.0').canonicalJson(f.asset),assetDigest=await hash(assetRaw),contextRaw=JSON.stringify({}),contextDigest=await hash(contextRaw);
 await savePackage(f.store,'account-a.package.course.'+assetDigest,{package:f.asset,payload_json:assetRaw,sha256:assetDigest});
 await savePackage(f.store,'account-a.package.context.'+contextDigest,{payload_json:contextRaw,sha256:contextDigest});
 const record={id:f.round.id,key:f.key,phase:'preparing',spec:{round:f.round,setup:f.disk.native_start.registration.setup,asset_sha256:assetDigest,context_sha256:contextDigest,package_sha256:f.envelope.sha256}};
 await f.store.setItem('account-a',JSON.stringify({schema:1,catalog:[],downloads:[],draft:{memory_allowed:true,patch:{},stage:'course',start_hole:1},rounds:[record],active_id:record.id}));
 const library=new CourseLibrary('https://offline.test','a',f.store,'account-a',randomUUID,hash);const materialized=await library.materialize(await library.active());
 assert.equal(materialized.package.sha256,f.envelope.sha256);assert.equal(materialized.package.package.core_version,'1.4.0');
 const local=new OfflineRound('https://offline.test','a',f.store,f.key,randomUUID,hash);await local.beginOffline(materialized);assert.equal((await local.verifyCached()).local_state.revision,f.state.revision);
});
test('frozen 1.5 also restores its original field shape and strategy after the 1.6 upgrade',async()=>{
 const f=await oldCheckpoint({core_version:'1.5.0'});const local=new OfflineRound('https://offline.test','a',f.store,f.key,randomUUID,hash);await local.verifyCached();
 const at=new Date().toISOString();await local.turn('以后优先保守打法','preference-after-upgrade',at);const disk=await local.verifyCached();assert.equal(disk.local_state.core_version,'1.5.0');assert.equal(disk.local_state.profile.strategy_preference.value,'control');assert.equal(disk.local_state.profile.field_versions,undefined);
 assert.equal((await local.strategy()).policy_version,1);
});
