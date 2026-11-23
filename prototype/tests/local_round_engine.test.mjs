import {CORE_VERSION,CORE_DATASET} from '../shared/core/protocol.ts';
import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import {spawnSync} from 'node:child_process';import {fileURLToPath} from 'node:url';
import {createLocalRound,applyLocalCommand,localTotals} from '../shared/core/roundEngine.ts';
const cases=JSON.parse(fs.readFileSync(new URL('./fixtures/local_round_cases.json',import.meta.url),'utf8'));
const pack={schema:1,core_version:CORE_VERSION,round:{id:'r',tee:'蓝Tee',start_hole:1},course:{course_id:'c',holes:Array.from({length:18},(_,i)=>({number:i+1,par:4}))}};
const python=process.env.CADDIE_TEST_PYTHON??process.env.PYTHON??'python3';
test('mobile rules and server validator have identical states after every accepted/rejected command',()=>{
 const run=spawnSync(python,[fileURLToPath(new URL('./local_engine_reference.py',import.meta.url))],{input:JSON.stringify(cases),encoding:'utf8',maxBuffer:16*1024*1024});assert.equal(run.status,0,run.stderr);const expected=JSON.parse(run.stdout);
 for(const [index,example] of cases.entries()){
  let s=createLocalRound(pack);
  for(const [i,step] of example.steps.entries()){
   const event={v:1,semantics:2,id:'e'+i,at:'2026-11-22T01:00:00+00:00',expected_revision:s.revision,command:step.command,data:step.data??{}};if(step.semantics!==undefined)event.semantics=step.semantics;const before=structuredClone(s);let error=false,message='';
   try{s=applyLocalCommand(s,event)}catch(e){if(e.name!=='Error')throw e;error=true;message=e.message}
   assert.equal(error,Boolean(step.error),example.name+' '+i);assert.equal(error,expected[index][i].error,example.name+' error parity');if(error)assert.equal(message,expected[index][i].message,example.name+' rejection reason');
   assert.deepEqual(s,expected[index][i].state,example.name+' state '+i);if(error)assert.deepEqual(s,before);
  }
  if(example.totals)assert.deepEqual(localTotals(s),example.totals);
  if(example.name==='ob-retee')assert.deepEqual(s.holes['1'].rows.at(-1).origin,example.steps[1].data.point);
 }
});
test('idempotent commands cannot silently change an existing event',()=>{
 const initial=createLocalRound(pack),event={v:1,semantics:2,id:'start',at:'2026-11-22T01:00:00Z',expected_revision:0,command:'start',data:{}};const s=applyLocalCommand(initial,event);assert.equal(applyLocalCommand(s,event),s);assert.throws(()=>applyLocalCommand(s,{...event,command:'record_stroke'}),/reused/);assert.equal(initial.revision,0);
});
test('an unknown landing cannot reuse the tee as the following shot origin',()=>{
 let s=createLocalRound(pack),n=0;const turn=(command,data={})=>s=applyLocalCommand(s,{v:1,semantics:2,id:'p'+(++n),at:'2026-11-22T01:00:00Z',expected_revision:s.revision,command,data});
 turn('start');turn('set_position',{point:{latitude:22.7,longitude:114.15,accuracy_m:2}});turn('record_stroke',{club:'一号木'});assert.equal(s.position,null);turn('set_landing',{lie:'green'});turn('record_stroke',{club:'推杆'});assert.equal(s.holes['1'].rows[1].origin,null);
});
test('a putter used from the fringe is not automatically a statistical putt',()=>{
 let s=createLocalRound(pack),n=0;const turn=(command,data={})=>s=applyLocalCommand(s,{v:1,semantics:2,id:'f'+(++n),at:'2026-11-22T01:00:00Z',expected_revision:s.revision,command,data});
 turn('start');turn('record_stroke',{club:'推杆',is_putt:false});turn('draft_score',{total:2,putts:1,penalties:0});turn('confirm_score',{confirmed:true});assert.equal(s.holes['1'].rows[0].is_putt,false);assert.equal(s.holes['1'].rows.length,2);assert.equal(s.holes['1'].score.putts,1);
});

test('known original landing is restored after resolving an uncertain OB report',()=>{
 let s=createLocalRound(pack),n=0;const turn=(command,data={})=>s=applyLocalCommand(s,{v:1,semantics:2,id:'o'+(++n),at:'2026-11-22T01:00:00Z',expected_revision:s.revision,command,data});
 const tee={latitude:22.7,longitude:114.15,accuracy_m:2},landing={latitude:22.701,longitude:114.151,accuracy_m:2};turn('start');turn('set_position',{point:tee});turn('record_stroke',{club:'一号木'});turn('report_incident',{cause:'possible_ob'});turn('set_landing',{point:landing});turn('resolve_ball',{result:'in_bounds'});assert.deepEqual(s.position,landing);
});

test('current fringe lie takes precedence over a previous green landing for putt statistics',()=>{
 let s=createLocalRound(pack),n=0;const turn=(command,data={})=>s=applyLocalCommand(s,{v:1,semantics:2,id:'lie'+(++n),at:'2026-01-01T00:00:00Z',expected_revision:s.revision,command,data});
 turn('start');turn('record_stroke',{club:'7号铁',lie:'green'});turn('set_lie',{lie:'fringe'});turn('record_stroke',{club:'推杆'});assert.equal(s.holes['1'].rows.at(-1).is_putt,false);
});
test('correcting an earlier landing does not move the current ball, and moving retains the club but clears stale aim',()=>{
 let s=createLocalRound(pack),n=0;const turn=(command,data={})=>s=applyLocalCommand(s,{v:1,semantics:2,id:'context'+(++n),at:'2026-01-01T00:00:00Z',expected_revision:s.revision,command,data});
 const a={latitude:31,longitude:121,accuracy_m:2},b={latitude:31.001,longitude:121,accuracy_m:2},c={latitude:31.002,longitude:121,accuracy_m:2};
 turn('start');turn('record_stroke',{club:'一号木',landing:a,lie:'fairway'});const first=s.holes['1'].rows[0].id;turn('record_stroke',{club:'7号铁',landing:b,lie:'green'});turn('set_landing',{stroke_id:first,point:c,lie:'bunker'});assert.deepEqual(s.position,b);assert.equal(s.lie,'green');
 turn('select_club',{club:'推杆',target:c});turn('set_position',{point:c});assert.equal(s.selection.club,'推杆');assert.equal(s.selection.target,null);
});

test('backfilling a previous hole preserves the current club and undo remains scoped',()=>{
 let s=createLocalRound(pack),n=0;const turn=(command,data={})=>s=applyLocalCommand(s,{v:1,semantics:2,id:'backscope'+(++n),at:'2026-01-01T00:00:00Z',expected_revision:s.revision,command,data});
 turn('start');turn('record_stroke',{club:'7号铁',lie:'green'});turn('navigate_hole',{hole:2});turn('select_club',{club:'7号铁'});turn('draft_score',{hole:1,total:3,putts:2,penalties:0});turn('confirm_score',{confirmed:true});assert.equal(s.hole,2);assert.equal(s.selection.club,'7号铁');assert.equal(s.holes['1'].score.total,3);assert.equal(s.holes['2'].score,null);
 turn('undo');assert.equal(s.hole,2);assert.equal(s.selection.club,'7号铁');assert.equal(s.holes['1'].score,null);assert.equal(s.draft.hole,1);
});

test('only explicitly versioned current commands and packages are accepted',()=>{
 const state=createLocalRound(pack),event={v:1,semantics:2,id:'strict',at:'2026-11-23T00:00:00Z',expected_revision:0,command:'start'};
 for(const semantics of [undefined,null,1,3])assert.throws(()=>applyLocalCommand(state,{...event,semantics}),/unsupported command semantics/);
 assert.equal(state.revision,0);const {core_version,...unversioned}=pack;assert.throws(()=>createLocalRound(unversioned),/version mismatch/);
});
