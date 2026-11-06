import test from 'node:test';
import assert from 'node:assert/strict';
import {newFlow,voiceTurn,parseScore,distanceAdvice} from '../apps/mobile/src/voiceFlow.ts';
test('a score is requested once at hole end and committed only after verbal confirmation',()=>{
 let flow=newFlow('round');
 let turn=voiceTurn(flow,'这洞打完了');assert.equal(turn.flow.phase,'awaitingScore');assert.equal(turn.text,'这洞一共几杆？');assert.equal(turn.save,undefined);
 flow=turn.flow;turn=voiceTurn(flow,'这洞打完了');assert.equal(turn.text.includes('一共几杆'),false);
 turn=voiceTurn(flow,'六杆，两推');assert.equal(turn.flow.phase,'confirming');assert.equal(turn.save,undefined);assert.equal(turn.flow.draft.penalty,null);
 turn=voiceTurn(turn.flow,'确认');assert.deepEqual(turn.save,{hole:0,score:{total:6,putts:2,penalty:null}});assert.equal(turn.flow.hole,1);
 assert.equal(voiceTurn(turn.flow,'确认').save,undefined);
});
test('corrections replace drafts, never silently overwrite scores',()=>{
 let flow=voiceTurn(newFlow('r'),'这洞打完了').flow;
 flow=voiceTurn(flow,'六杆').flow;const corrected=voiceTurn(flow,'不对，是七杆，一罚，两推');
 assert.equal(corrected.flow.draft.total,7);assert.equal(corrected.flow.draft.penalty,1);assert.equal(corrected.save,undefined);
 assert.equal(voiceTurn(corrected.flow,'取消').flow.draft,null);
});
test('skip preserves absence, silence pauses, and ball-in-play never demands a score',()=>{
 let initial=newFlow('r');assert.equal(voiceTurn(initial,'我准备击球').handled,false);
 let waiting=voiceTurn(initial,'这洞结束了').flow;
 const skip=voiceTurn(waiting,'先不记');assert.equal(skip.flow.hole,1);assert.equal(skip.save,undefined);assert.equal(skip.flow.phase,'playing');
 const quiet=voiceTurn(waiting,'安静');assert.equal(quiet.pause,true);assert.equal(quiet.save,undefined);assert.equal(quiet.flow.phase,'awaitingScore');
});
test('unknown secondary stats stay null, invalid scores do not become drafts',()=>{
 assert.deepEqual(parseScore('六杆'),{total:6,penalty:null,putts:null});
 assert.deepEqual(parseScore('十六杆，一罚，三推'),{total:16,penalty:1,putts:3});
 assert.equal(parseScore('三杆，两罚，两推'),null);assert.equal(parseScore('一百六杆'),null);assert.equal(parseScore('6.5杆'),null);
 assert.equal(parseScore('七号铁一百四十米'),null);
});
test('hole 18 completes without asking for hole 19',()=>{
 let flow=voiceTurn(newFlow('r',17),'这洞结束了').flow;
 flow=voiceTurn(flow,'五杆').flow;const last=voiceTurn(flow,'确认');
 assert.equal(last.flow.phase,'finished');assert.equal(last.save.hole,17);assert.equal(last.text.includes('19'),false);
});
test('distance suggestions use only confirmed carry facts, never assume wind or hazards',()=>{
 const clubs=[{name:'七号铁',distance:140,distanceType:'carry',source:'user_confirmed'}, {name:'六号铁',distance:155,distanceType:'carry',source:'user_confirmed'}, {name:'总距离球杆',distance:145,distanceType:'total',source:'user_confirmed'}];
 const answer=distanceAdvice('还剩145米',clubs);assert.ok(answer.includes('七号铁'));assert.ok(answer.includes('少5米'));assert.ok(answer.includes('六号铁'));assert.ok(!answer.includes('总距离球杆'));assert.ok(answer.includes('只作距离参考'));
 assert.ok(distanceAdvice('目标150码',clubs));assert.equal(distanceAdvice('我紧张',clubs),null);
});
