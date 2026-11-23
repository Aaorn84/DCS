import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import {createHash,randomUUID} from 'node:crypto';
import {CORE_VERSION,CORE_DATASET} from '../shared/core/protocol.ts';
import {createLocalRound} from '../shared/core/roundEngine.ts';
import {webJourneyTurn} from '../shared/core/webJourney.ts';
import {planStrategy} from '../shared/core/strategy.ts';
import {personalStrategy} from '../shared/core/personalStrategy.ts';
import {conservativeTee,resolveStrategyPolicy,STRATEGY_POLICY_VERSION} from '../shared/core/strategyPolicy.ts';
import {OfflineRound} from '../apps/mobile/src/offlineRound.ts';
const reported=distance=>({value:{distance,distance_type:'carry',units:'码'},source:'user_report'});
function fixture(){
 const course=JSON.parse(fs.readFileSync(new URL('../services/api/assets/phoenix-demo.json',import.meta.url),'utf8'));
 const pack={schema:1,core_version:CORE_VERSION,dataset:CORE_DATASET,local_command_semantics:2,local_rules_version:1,round:{id:'finder-round-123',course:course.course_id,tee:'蓝Tee',start_hole:1,started_at:new Date().toISOString()},course,profile:{driver:reported(260),seven:reported(160)}};
 const model=createLocalRound(pack);model.stage='playing';model.position=course.holes[0].simulation_positions.tee;return {pack,model};
}
test('Phoenix dialogue remembers finder and gives its feasible comparable route without asking the same details',()=>{
 const f=fixture();let model=f.model,context={};let id=0;
 const say=text=>{const reply=webJourneyTurn(f.pack,model,{type:'message',event_id:'finder-'+(++id),observed_at:new Date().toISOString(),text},context);model=reply.model;context=reply.context;return reply;};
 const first=say('有没有保守方案');assert.equal(first.strategy.question,'finder_club');assert.equal(first.strategy.options.length,0);assert.match(first.text,/保底开球杆.*Carry/);
 const recorded=say('保底开球杆 5号木 200码');assert.equal(recorded.strategy.options[0].club,'5号木');assert.equal(recorded.strategy.options[0].carry_yards,200);assert.match(recorded.text,/已记录保底开球杆和Carry/);assert.match(recorded.text,/地图比较未显示风险明显降低/);
 const again=say('有没有保守方案');assert.equal(again.strategy.options[0].club,'5号木');assert.equal(again.strategy.comparison,'comparable_finder');assert.doesNotMatch(again.text,/请补充保底开球杆|稳定Carry大概多少/);assert.equal(model.holes['1'].rows.length,0);assert.equal(model.selection,null);
});
test('phone replans the pending conservative request when finder and Carry are supplied offline',async()=>{
 const previous=globalThis.fetch;const f=fixture(),data=new Map();const hash=async s=>createHash('sha256').update(s).digest('hex');let calls=0;
 try{
  globalThis.fetch=async()=>{calls++;throw Error('offline')};const store={getItem:async k=>data.get(k)??null,setItem:async(k,v)=>data.set(k,v)};
  const local=new OfflineRound('https://offline.invalid','a',store,'finder-local',randomUUID,hash),payload_json=JSON.stringify(f.pack);
  await local.beginOffline({round:f.pack.round,asset_sha256:'a'.repeat(64),context_sha256:'b'.repeat(64),setup:{memory_allowed:true,patch:{}},package:{package:f.pack,payload_json,sha256:await hash(payload_json),source_version:0}});
  const at=new Date().toISOString();await local.execute('set_position',{point:f.model.position},'position',at);
  await local.turn('有没有保守方案','first',at);const recorded=await local.turn('保底开球杆 5号木 200码','finder',at);
  assert.equal(recorded.strategy.options[0].club,'5号木');const revision=recorded.local_state.revision;
  const again=await local.turn('有没有保守方案','again',at);assert.equal(again.strategy.options[0].club,'5号木');assert.equal(again.local_state.revision,revision);assert.equal(again.local_state.holes['1'].rows.length,0);assert.equal(calls,0);
 }finally{globalThis.fetch=previous;}
});
test('a finder with no mapped landing is acknowledged as known instead of requesting its Carry again',()=>{
 const f=fixture();f.model.profile.fairway_finder={value:{club:'5号木'},source:'user_report'};f.model.profile.five_wood=reported(200);
 // Known Carry cannot create a fairway landing when there are no mapped fairway polygons.
 for(const h of f.pack.course.holes)h.surface_zones=(h.surface_zones??[]).filter(z=>z.surface!=='fairway');
 f.pack.course.reference_simulation=false;
 const result=planStrategy(f.pack,f.model,{kind:'conservative'});assert.equal(result.options.length,0);assert.equal(result.unavailable_reason,'finder_landing');assert.match(result.text,/保底开球杆和Carry已记录/);assert.doesNotMatch(result.text,/请补充保底|大概多少/);
});
test('trusted club status never bypasses mapped penalty, bunker or repeated local miss risk',()=>{
 const personal=personalStrategy({fairway_finder:{value:{club:'5号木'}}}),policy=resolveStrategyPolicy(personal,'conservative');
 const baseline={club:'一号木',penalty_samples:0,bunker_samples:0,history_weight:0,risk:0,progress:260,width_yards:45};
 const finder={...baseline,club:'5号木',progress:200,width_yards:30};
 assert.equal(conservativeTee([finder],baseline,personal,policy).selected.club,'5号木');
 for(const extra of [{penalty_samples:1,risk:30},{history_weight:1,risk:20},{bunker_samples:1,risk:4},{nearby:['water']},{nearby:['ob']}])assert.equal(conservativeTee([{...finder,...extra}],baseline,personal,policy).selected,undefined);
});
test('without a finder, mapped estimated long irons remain alternatives and keep the estimate label',()=>{
 const f=fixture();const result=planStrategy(f.pack,f.model,{kind:'alternative'});const row=result.options[0];
 assert.equal(row.club,'3号铁');assert.equal(row.carry_yards,200);assert.equal(row.estimated,true);assert.equal(result.comparison,'comparable_alternative');assert.match(result.text,/按7号铁杆距暂估/);assert.match(result.text,/地图比较未显示风险明显降低/);assert.doesNotMatch(result.text,/请补充.*保底|设置保底/);
});
test('without a finder, reported 3/4/5 irons are all considered and distance breaks equal-risk ties',()=>{
 const personal=personalStrategy({}),policy=resolveStrategyPolicy(personal,'conservative');
 const base={club:'一号木',penalty_samples:0,bunker_samples:0,history_weight:0,risk:0,progress:260,width_yards:45};
 const rows=[{...base,club:'5号铁',progress:180,width_yards:30},{...base,club:'4号铁',progress:190,width_yards:30},{...base,club:'3号铁',progress:200,width_yards:30}];
 assert.equal(conservativeTee(rows,base,personal,policy).selected.club,'3号铁');
 assert.equal(conservativeTee(rows.map(r=>r.club==='3号铁'?{...r,penalty_samples:1,risk:30}:r),base,personal,policy).selected.club,'4号铁');
 assert.equal(conservativeTee(rows.map(r=>r.club!=='5号铁'?{...r,nearby:['water']}:r),base,personal,policy).selected.club,'5号铁');
});
test('a lack of mapped alternatives does not turn configuring a finder into a prerequisite',()=>{
 const f=fixture();f.pack.course.reference_simulation=false;for(const h of f.pack.course.holes)h.surface_zones=(h.surface_zones??[]).filter(z=>z.surface!=='fairway');
 const result=planStrategy(f.pack,f.model,{kind:'alternative'});assert.equal(result.options.length,0);assert.doesNotMatch(result.text,/保底/);assert.match(result.text,/补充Carry|现场确认/);
});
test('a configured finder is not preferred over an alternative with clearly less primary hazard exposure',()=>{
 const personal=personalStrategy({fairway_finder:{value:{club:'5号木'}}}),policy=resolveStrategyPolicy(personal,'conservative');
 const base={club:'一号木',penalty_samples:0,bunker_samples:2,history_weight:0,risk:8,progress:260,width_yards:45};
 const finder={...base,club:'5号木',bunker_samples:1,risk:4,progress:200,width_yards:30},iron={...base,club:'4号铁',bunker_samples:0,risk:0,progress:190,width_yards:30};
 assert.equal(conservativeTee([finder,iron],base,personal,policy).selected.club,'4号铁');
});
test('a bunker-purpose-only wedge is not turned into an invented tee Carry alternative',()=>{
 const f=fixture();f.model.profile={lofted_wedge_uses:{value:{'58':'沙坑'},source:'user_report'}};
 const result=planStrategy(f.pack,f.model,{kind:'alternative'});assert.equal(result.options.length,0);assert.doesNotMatch(result.text,/58度杆Carry/);
});
test('stored old-policy no-option replies are invalidated without disabling the current policy cache',()=>{
 const f=fixture(),intent={kind:'conservative'},context={advice:{revision:f.model.revision,intent,intent_key:JSON.stringify(intent),plan:{core_version:CORE_VERSION,policy_version:1,question:null,options:[],text:'请补充保底开球杆'}}};
 const event={type:'message',event_id:'policy-refresh',observed_at:new Date().toISOString(),text:'有没有保守方案'};
 const fresh=webJourneyTurn(f.pack,f.model,event,context);assert.equal(fresh.flags.strategy_cache_hit,false);assert.equal(fresh.strategy.question,'finder_club');assert.equal(fresh.strategy.policy_version,STRATEGY_POLICY_VERSION);
 const repeat=webJourneyTurn(f.pack,fresh.model,{...event,event_id:'policy-repeat'},fresh.context);assert.equal(repeat.flags.strategy_cache_hit,true);assert.equal(repeat.strategy.question,'finder_club');
});
test('conservative asks for missing trusted club while other plans can use estimates immediately',()=>{
 const f=fixture();const conservative=planStrategy(f.pack,f.model,{kind:'conservative'});assert.equal(conservative.question,'finder_club');assert.equal(conservative.options.length,0);
 const alternative=planStrategy(f.pack,f.model,{kind:'alternative'});assert.equal(alternative.question,null);assert.equal(alternative.options[0].club,'3号铁');assert.equal(alternative.options[0].estimated,true);
});
test('a bare trusted club reply is personal setup, asks only for missing Carry and never selects a shot',()=>{
 const f=fixture();let model=f.model,context={};let n=0;
 const say=text=>{const r=webJourneyTurn(f.pack,model,{type:'message',event_id:'setup-'+(++n),observed_at:new Date().toISOString(),text},context);model=r.model;context=r.context;return r;};
 say('有没有保守方案');const club=say('5号木');assert.equal(club.strategy.question,'finder_carry');assert.equal(model.profile.fairway_finder.value.club,'5号木');assert.equal(model.selection,null);
 const carry=say('200');assert.equal(carry.strategy.options[0].club,'5号木');assert.equal(carry.strategy.options[0].carry_yards,200);assert.equal(model.selection,null);assert.equal(model.holes['1'].rows.length,0);
 for(const question of ['有没有保守方案','有没有其他方案']){const r=say(question);assert.equal(r.strategy.question,null);assert.equal(r.strategy.options[0].club,'5号木');assert.doesNotMatch(r.text,/大概多少|哪支杆/);}
});
test('a combined unprefixed answer records both the trusted club and its Carry',()=>{
 const f=fixture();const first=webJourneyTurn(f.pack,f.model,{type:'message',event_id:'q',observed_at:new Date().toISOString(),text:'有没有保守方案'});
 const r=webJourneyTurn(f.pack,first.model,{type:'message',event_id:'answer',observed_at:new Date().toISOString(),text:'5号木200码'},first.context);
 assert.equal(r.model.profile.fairway_finder.value.club,'5号木');assert.equal(r.model.profile.bag_overrides['5号木'].high,200);assert.equal(r.strategy.options[0].club,'5号木');assert.equal(r.model.selection,null);
});
test('an incomplete configured finder blocks only conservative setup, not other-plan comparisons',()=>{
 const f=fixture();f.model.profile.fairway_finder={value:{club:'5号木'},source:'user_report'};
 assert.equal(planStrategy(f.pack,f.model,{kind:'conservative'}).question,'finder_carry');const other=planStrategy(f.pack,f.model,{kind:'alternative'});assert.equal(other.question,null);assert.equal(other.options[0].club,'3号铁');
 f.model.profile.fairway_finder={value:{club:'4号铁'},source:'user_report'};assert.equal(planStrategy(f.pack,f.model,{kind:'conservative'}).question,'finder_carry');
});
test('both initial requests prefer a complete trusted club even if it is also the default recommendation',()=>{
 const f=fixture();f.model.profile.fairway_finder={value:{club:'一号木'},source:'user_report'};
 for(const kind of ['conservative','alternative']){const r=planStrategy(f.pack,f.model,{kind});assert.equal(r.question,null);assert.equal(r.options[0].club,'一号木');}
});
