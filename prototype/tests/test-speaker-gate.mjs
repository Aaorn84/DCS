import {test} from 'node:test';
import assert from 'node:assert/strict';
import {enroll,matches,verifyThenTranscribe} from '../apps/mobile/src/speakerGate.ts';
const owner=Array.from({length:32},(_,i)=>i<16?1:0);
const other=Array.from({length:32},(_,i)=>i>=16?1:0);
const template=enroll([owner,owner.map(v=>v*2),owner]);
const profile={enabled:true,template};
test('three consistent samples form a template; mixed enrollment is refused',()=>{
 assert.ok(template);assert.equal(enroll([owner,owner,other]),null);
 assert.equal(enroll([owner,owner]),null);assert.equal(enroll([owner,owner.map(()=>0),owner]),null);
 assert.equal(matches(template,owner),true);assert.equal(matches(template,other),false);
});
test('only a matching clip reaches transcription and can yield a command',async()=>{
 let calls=0;
 const input={profile,durationMs:1800,isCurrent:()=>true,embedding:async()=>owner,transcribe:async()=>{calls++;return ' 五杆 ';}};
 assert.equal(await verifyThenTranscribe({...input,embedding:async()=>other}),null);
 assert.equal(calls,0);
 assert.equal(await verifyThenTranscribe(input),'五杆');assert.equal(calls,1);
});
test('unavailable verification, invalid template and undersized clips fail closed',async()=>{
 let calls=0;
 const input={profile,durationMs:1800,isCurrent:()=>true,embedding:async()=>owner,transcribe:async()=>{calls++;return '确认';}};
 for(const override of [{embedding:async()=>{throw Error('model unavailable');}},
   {profile:{enabled:true,template:'invalid'}},{durationMs:900},{durationMs:NaN},{profile:{enabled:false,template}}]){
  assert.equal(await verifyThenTranscribe({...input,...override}),null);
 }
 assert.equal(calls,0);
});
test('cancellation during inference prevents transcription',async()=>{
 let active=true;
 const out=await verifyThenTranscribe({profile,durationMs:1800,isCurrent:()=>active,
   embedding:async()=>{active=false;return owner;},transcribe:async()=>assert.fail('no transcription after cancellation')});
 assert.equal(out,null);
});
test('late transcript from cancelled session cannot become a command',async()=>{
 let active=true;
 const out=await verifyThenTranscribe({profile,durationMs:1800,isCurrent:()=>active,embedding:async()=>owner,
   transcribe:async()=>{active=false;return '五杆';}});
 assert.equal(out,null);
});
