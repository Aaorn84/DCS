import test from 'node:test';import assert from 'node:assert/strict';
import {setupProfile} from '../shared/core/offlineSetup.ts';
import {stampProfileChanges,profileFacts,profileFromFacts} from '../shared/core/profileMemory.ts';
const clock=(at,order=1)=>({at,round_id:'round-profile',order});
test('field merge protects newer Carry while allowing an unrelated older field and a new explicit edit',()=>{
 const base=setupProfile({},{carries:{'7号铁':{low:175,high:175}},field_versions:{'bag:7号铁':clock('2026-11-22T00:00:00Z'),seven:clock('2026-11-22T00:00:00Z')}});
 const result=setupProfile(base,{carries:{'7号铁':{low:160,high:160},'3号木':{low:210,high:210}},field_versions:{'bag:7号铁':clock('2026-11-20T00:00:00Z'),seven:clock('2026-11-20T00:00:00Z'),'bag:3号木':clock('2026-11-20T00:00:00Z')}});
 const tied=setupProfile(base,{carries:{'7号铁':{low:155,high:155}},field_versions:{'bag:7号铁':clock('2026-11-22T08:00:00+08:00',0),seven:clock('2026-11-22T08:00:00+08:00',0)}});assert.equal(tied.bag_overrides['7号铁'].high,175);
 assert.equal(result.bag_overrides['7号铁'].high,175);assert.equal(result.seven.value.distance,175);assert.equal(result.bag_overrides['3号木'].high,210);
 const after=setupProfile(result,{carries:{'7号铁':{low:180,high:180}}});stampProfileChanges(result,after,clock('2026-11-23T00:00:00Z'));assert.equal(after.bag_overrides['7号铁'].high,180);assert.equal(after.field_versions['bag:7号铁'].at,'2026-11-23T00:00:00Z');
});
test('profile wire facts preserve ranges and purposes without promoting estimated distances',()=>{
 const p=setupProfile({},{carries:{'52度杆':{low:0,high:85}},purposes:{'58':'沙坑'},finder:'5号木',fairway_status:'unknown'});
 assert.equal(setupProfile({personal_note:{value:'喜欢安静',source:'user_report'}},{}).personal_note.value,'喜欢安静');
 assert.deepEqual(profileFromFacts(profileFacts(p)),p);assert.equal(setupProfile(p,{finder:null}).fairway_finder,null);
 assert.throws(()=>setupProfile({}, {purposes:{'7':'沙坑'}}));assert.throws(()=>setupProfile({}, {field_versions:{seven:{at:'bad',round_id:'r',order:1}}}));
});
test('undo restores both Carry and its field clock without generating a newer write',async()=>{
 const {createLocalRound,applyLocalCommand}=await import('../shared/core/roundEngine.ts');const {CORE_VERSION}=await import('../shared/core/protocol.ts');
 let s=createLocalRound({schema:1,core_version:CORE_VERSION,round:{id:'profile-round',tee:'蓝Tee'},profile:{},course:{course_id:'c',holes:Array.from({length:18},(_,i)=>({number:i+1,par:4}))}});
 const run=(command,data={},id=command)=>s=applyLocalCommand(s,{v:1,semantics:2,id,at:'2026-11-22T00:00:00Z',expected_revision:s.revision,command,data});
 run('start');run('set_club_carry',{club:'7号铁',low:175,high:175});const saved=structuredClone(s.profile);run('set_club_carry',{club:'7号铁',low:180,high:180},'second-carry');run('undo');assert.deepEqual(s.profile,saved);
});
