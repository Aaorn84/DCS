import test from 'node:test';
import assert from 'node:assert/strict';
import {personalStrategy,appendStrategyUsage,parseStrategyPreference} from '../shared/core/personalStrategy.ts';
import {rankCandidates,chooseTee,resolveStrategyPolicy,systemRisk} from '../shared/core/strategyPolicy.ts';
import {createLocalRound,applyLocalCommand} from '../shared/core/roundEngine.ts';
import {parseLocalTurn} from '../shared/core/dialogue.ts';
import {webJourneyTurn} from '../shared/core/webJourney.ts';
import {CORE_VERSION,CORE_DATASET} from '../shared/core/protocol.ts';
const row=(club,progress,fields={})=>({club,progress,width_yards:35,penalty_samples:0,history_weight:0,bunker_samples:0,rough_samples:0,risk:0,...fields});
const pack=()=>({schema:1,core_version:CORE_VERSION,dataset:CORE_DATASET,local_rules_version:1,local_command_semantics:2,round:{id:'round-id',tee:'蓝Tee',start_hole:1},profile:{},course:{course_id:'map',holes:Array.from({length:18},(_,i)=>({number:i+1,par:4}))}});
const start=()=>{const p=pack();let s=createLocalRound(p);s=applyLocalCommand(s,{v:1,semantics:2,id:'start',at:'2026-11-23T00:00:00Z',expected_revision:0,command:'start'});return {p,s};};
test('system policy is map independent and default prioritizes a checked driver',()=>{
 const personal=personalStrategy({});const policy=resolveStrategyPolicy(personal);
 assert.equal(chooseTee([row('一号木',260),row('5号木',220)],policy,personal).club,'一号木');
 assert.equal(systemRisk(row('x',1,{penalty_samples:1,bunker_samples:1})),34);
 assert.equal(personal.source,'system_default');
});
test('personal preference ranks comparable candidates but never overrides penalty exposure',()=>{
 const personal=personalStrategy({strategy_preference:{value:'control',source:'user_report'},fairway_finder:{value:{club:'5号木'}}});const policy=resolveStrategyPolicy(personal);
 assert.equal(chooseTee([row('一号木',220),row('5号木',210)],policy,personal).club,'5号木');
 assert.equal(chooseTee([row('一号木',220),row('5号木',210,{penalty_samples:1,risk:30})],policy,personal).club,'一号木');
 assert.equal(resolveStrategyPolicy(personal,'aggressive').mode,'distance');
 assert.equal(resolveStrategyPolicy(personalStrategy({}),'conservative').mode,'control');
});
test('choices require eight samples across three rounds and never infer intent from a miss',()=>{
 const profile={};for(let i=0;i<7;i++)appendStrategyUsage(profile,'r'+i%3,i,'control');
 assert.equal(personalStrategy(profile).source,'system_default');appendStrategyUsage(profile,'r2',8,'control');
 assert.equal(personalStrategy(profile).source,'observed_choices');assert.equal(personalStrategy(profile).preference,'control');
 profile.strategy_preference={value:'distance',source:'user_report'};assert.equal(personalStrategy(profile).preference,'distance');
 assert.equal(personalStrategy({usual_miss:{value:'偏右'}}).source,'system_default');
 const snapshot=structuredClone(profile);personalStrategy(profile);assert.deepEqual(profile,snapshot);
});
test('one observation per hole, bounded history and evolving dispersion confidence',()=>{
 const profile={};for(let i=0;i<90;i++)appendStrategyUsage(profile,'r'+i,i,'control');assert.equal(profile.strategy_usage.length,60);
 appendStrategyUsage(profile,'r89',89,'distance');assert.equal(profile.strategy_usage.length,60);
 const observed=samples=>({'5号木':{samples,lateral_p10_m:-10,lateral_p90_m:12}});
 assert.deepEqual(personalStrategy({},observed(9)).trusted_clubs,[]);
 assert.equal(personalStrategy({},observed(10)).evidence['5号木'].confidence,'developing');
 assert.deepEqual(personalStrategy({},observed(30)).trusted_clubs,['5号木']);
});
test('long term preference grammar differs from a one shot request in web and shared command',()=>{
 assert.equal(parseStrategyPreference('有没有保守方案'),null);assert.equal(parseStrategyPreference('以后优先稳妥打法'),'control');
 const {p,s}=start();const turn=webJourneyTurn(p,s,{type:'message',event_id:'pref',observed_at:'2026-11-23T00:00:01Z',text:'以后优先保守打法'});
 assert.equal(turn.model.profile.strategy_preference.value,'control');assert.equal(turn.model.holes['1'].rows.length,0);
 assert.deepEqual(parseLocalTurn(s,'有没有保守方案').commands,[]);
});
test('selection alone never trains habits; stroke trains once; undo restores the profile',()=>{
 const {s}=start();const apply=(m,id,command,data={})=>applyLocalCommand(m,{v:1,semantics:2,id,at:'2026-11-23T00:00:01Z',expected_revision:m.revision,command,data});
 const selected=apply(s,'sel','select_club',{club:'5号木',strategy_choice:'control'});assert.equal(selected.profile.strategy_usage,undefined);
 const hit=apply(selected,'hit','record_stroke');assert.equal(hit.profile.strategy_usage.length,1);
 assert.equal(applyLocalCommand(hit,hit.receipts.hit).profile.strategy_usage.length,1);
 assert.equal(apply(hit,'undo','undo').profile.strategy_usage,undefined);
 assert.throws(()=>apply(s,'bad','set_strategy_preference',{preference:'ignore_ob'}));
 const incident=apply(hit,'incident','report_incident',{cause:'possible_ob'});assert.throws(()=>apply(incident,'pref','set_strategy_preference',{preference:'control'}),/resolve ball/);
});
