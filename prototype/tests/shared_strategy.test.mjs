import {CORE_VERSION,CORE_DATASET} from '../shared/core/protocol.ts';
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createLocalRound,applyLocalCommand} from '../shared/core/roundEngine.ts';
import {planStrategy} from '../shared/core/strategy.ts';
import {bag} from '../shared/core/bag.ts';
import {surfaces,contains,crossings,landingOffsets} from '../shared/core/geometry.ts';
const origin={latitude:31,longitude:121,accuracy_m:1},YARD=.9144,scale=111195*Math.cos(31*Math.PI/180);
const point=(x,y)=>({longitude:121+x*YARD/scale,latitude:31+y*YARD/111195,accuracy_m:0});
const rect=(id,surface,left,bottom,right,top)=>({id,surface,verified:true,source:'synthetic-test',geometry:{type:'Polygon',coordinates:[[[left,bottom],[right,bottom],[right,top],[left,top],[left,bottom]].map(([x,y])=>{const p=point(x,y);return [p.longitude,p.latitude];})]}});
const reported=n=>({value:{distance:n,distance_type:'carry',units:'码'}});
function fixture({par=4,length=400,driver=260,wood=240,greenAt=400,greenWidth=35,greenDepth=25,zones=[]}={}){
 const profile={driver:reported(driver),three_wood:reported(wood),five_wood:reported(200),seven:reported(160),fairway_finder:{value:{club:'5号木'}}};
 const p=point(0,0),green=point(0,greenAt),lo=point(-5,-5),hi=point(5,5);
 const hole={number:1,par,published_yardage:length,tee_bbox:[lo.longitude,lo.latitude,hi.longitude,hi.latitude],objects:[{...green,id:'green',kind:'green_center'}],surface_zones:[rect('fairway','fairway',-45,5,45,greenAt+greenDepth/2),rect('green','green',-greenWidth/2,greenAt-greenDepth/2,greenWidth/2,greenAt+greenDepth/2),...zones]};
 const pack={schema:1,local_rules_version:1,dataset:CORE_DATASET,local_command_semantics:2,core_version:'1.7.0',round:{id:'r',tee:'蓝Tee',start_hole:1},profile,course:{course_id:'c',crs:'WGS84',holes:Array.from({length:18},(_,i)=>({...hole,number:i+1}))}};
 let model=createLocalRound(pack);model=applyLocalCommand(model,{v:1,semantics:2,id:'start',at:'2026-01-01T00:00:00Z',expected_revision:0,command:'start'});model.position={...p,accuracy_m:1};
 return {pack,model,hole:pack.course.holes[0]};
}
function approach(f){f.model.holes['1'].rows=[{kind:'stroke',active:true,club:'一号木',lie:'fairway'}];f.model.lie='fairway';f.model.pins['1']={depth:'middle',side:'center'};return f;}
test('a cleared bunker on the aim line does not eliminate the driver and default stays one option',()=>{
 const {pack,model}=fixture({zones:[rect('b','bunker',-8,170,8,185)]});const result=planStrategy(pack,model);
 assert.equal(result.options.length,1);assert.equal(result.options[0].club,'一号木');assert.ok(result.options[0].crossings.some(c=>c.kind==='bunker'));assert.doesNotMatch(result.text,/一号木方案|历史参考/);
});
test('a conservative request uses the mapped finder when its hazard exposure improves',()=>{
 const {pack,model}=fixture({driver:240,zones:[rect('b','bunker',3,226,35,253)]});
 const result=planStrategy(pack,model,{kind:'conservative',exclude_club:'一号木'});assert.equal(result.options.length,1);assert.equal(result.options[0].club,'5号木');assert.match(result.text,/保底开球杆/);assert.doesNotMatch(result.text,/一号木Carry/);
});
test('par-five impossible distance prunes two-on geometry; missing long-club knowledge asks first',()=>{
 const f=fixture({par:5,length:570,greenAt:520});const r=planStrategy(f.pack,f.model);assert.equal(r.two_on_evaluated,false);assert.equal(r.two_on_excluded_reason,'distance_budget');assert.match(r.text,/三杆上/);
 delete f.model.profile.three_wood;delete f.model.profile.five_wood;const missing=planStrategy(f.pack,f.model);assert.equal(missing.question,'fairway_carry');assert.doesNotMatch(missing.text,/[34]号铁.*多少/);
});
test('par-five within ten yards retains two-on assessment',()=>{
 const f=fixture({par:5,length:510,greenAt:500});const r=planStrategy(f.pack,f.model);assert.equal(r.two_on_evaluated,true);assert.equal(r.two_on_excluded_reason,undefined);
});
test('seven-iron range approach stays a single direct option with a club and preserves input',()=>{
 const f=approach(fixture({greenAt:160})),before=structuredClone(f.model);const r=planStrategy(f.pack,f.model);assert.equal(r.options.length,1);assert.match(r.options[0].club,/铁|P杆/);assert.deepEqual(f.model,before);assert.doesNotMatch(r.text,/两上候选|三上候选/);
});
test('a roll-in needs a mapped clear ground route and never requires an unsupported long Carry',()=>{
 const f=approach(fixture({greenAt:250,greenDepth:8,greenWidth:8,wood:240}));const r=planStrategy(f.pack,f.model);assert.equal(r.options[0].club,'3号木');assert.ok(r.options[0].roll_yards>0&&r.options[0].roll_yards<=10);
 const blocked=approach(fixture({greenAt:250,greenDepth:8,greenWidth:8,wood:240,zones:[rect('water','water',-10,241,10,246)]}));const b=planStrategy(blocked.pack,blocked.model);assert.ok(!b.options.some(o=>o.club==='3号木'&&o.roll_yards>0));
});
test('an unreachable direct approach produces a middle-iron transition that advances the ball',()=>{
 const f=approach(fixture({greenAt:280,greenWidth:10,greenDepth:8}));const r=planStrategy(f.pack,f.model);assert.ok(r.options.length);assert.ok(r.options.every(o=>!o.club.endsWith('号木')));assert.ok(r.options[0].carry_yards>=160);assert.ok(r.options[0].remaining_yards<130);
});
test('pin, lie, clock-independent profile and unknown coordinates remain explicit state',()=>{
 const f=fixture({par:3,greenAt:160});const cmd=(command,data)=>f.model=applyLocalCommand(f.model,{v:1,semantics:2,id:'c'+f.model.revision,at:'2026-01-01T00:00:00Z',expected_revision:f.model.revision,command,data});
 assert.equal(planStrategy(f.pack,f.model).question,'pin');cmd('set_pin',{depth:'middle',side:'center'});assert.ok(planStrategy(f.pack,f.model).options.length);
 cmd('set_club_carry',{club:'5号铁',low:175,high:180});assert.equal(bag(f.model.profile).find(c=>c.label==='5号铁').high,180);
 cmd('record_stroke',{club:'7号铁'});assert.equal(planStrategy(f.pack,f.model).question,'position');
});
test('deep rough does not loop the clean-contact question or use full fairway Carry',()=>{
 const f=approach(fixture({greenAt:120}));f.model.lie='rough';f.model.clean_contact=false;const r=planStrategy(f.pack,f.model);assert.equal(r.question,null);assert.match(r.text,/深草先脱困/);assert.equal(r.options.length,0);
});
test('geometry respects holes, crossing edges and simulation cache scope',()=>{
 const f=fixture(),zone=rect('water','water',-10,80,10,100),all=surfaces({...f.hole,surface_zones:[zone]});const hit=crossings(all,origin,point(0,200));assert.equal(hit.length,1);assert.ok(Math.abs(hit[0].far_m-100*YARD)<.1);
 const outer=rect('g','green',-10,-10,10,10),inner=rect('inner','green',-2,-2,2,2);outer.geometry.coordinates.push(inner.geometry.coordinates[0]);const s=surfaces({surface_zones:[outer]})[0];assert.equal(contains(s,point(0,0)),false);
 const simulated={display_paths:[{id:'demo',kind:'GreenTrace',points:[point(-5,0),point(5,0),point(0,10)]}]};assert.equal(surfaces(simulated,true).length,1);assert.equal(surfaces(simulated,false).length,0);
});
test('same shared strategy executes through the persistent backend with identical results',()=>{
 const cases=[fixture(),fixture({par:5,length:570,greenAt:520}),approach(fixture({greenAt:130})),approach(fixture({greenAt:280}))];
 const code="import json,sys;sys.path.insert(0,'prototype/services/api');from shared_core import call;rows=json.load(sys.stdin);json.dump([call('plan',package=r['pack'],state=r['model']) for r in rows],sys.stdout,ensure_ascii=False)";
 const run=spawnSync(process.env.CADDIE_TEST_PYTHON??'python3',['-c',code],{input:JSON.stringify(cases),encoding:'utf8',maxBuffer:8*1024*1024});assert.equal(run.status,0,run.stderr);assert.deepEqual(JSON.parse(run.stdout),cases.map(f=>planStrategy(f.pack,f.model)));
});
test('source Phoenix tee scenarios run through the same core without hole-specific conditions',()=>{
 const course=JSON.parse(fs.readFileSync(new URL('../services/api/assets/phoenix-demo.json',import.meta.url),'utf8'));
 for(const hole of course.holes){const f=fixture();f.pack.course=course;f.model.hole=hole.number;f.model.position=hole.simulation_positions.tee;const r=planStrategy(f.pack,f.model);assert.equal(typeof r.text,'string');assert.ok(r.text.length);for(const o of r.options){assert.ok(o.carry_yards>0&&o.carry_yards<=400);assert.ok(!['ob','water','bunker'].some(kind=>surfaces(hole,true).some(s=>s.kind===kind&&contains(s,o.landing_point,true))));}}
});
test('local strategy is offline, captures only a current confirmed target, and invalidates by round/package',async()=>{
 const {OfflineRound}=await import('../apps/mobile/src/offlineRound.ts');const {createHash}=await import('node:crypto');const previous=globalThis.fetch,rows=new Map();
 const hash=async s=>createHash('sha256').update(s).digest('hex');const store={getItem:async k=>rows.get(k)??null,setItem:async(k,v)=>rows.set(k,v),removeItem:async k=>rows.delete(k)};
 const a=fixture(),b=fixture({greenAt:500});b.pack.round.id='new-round';let active=a,requests=0;
 const stateFor=f=>{let s=createLocalRound(f.pack);for(const [i,[command,data]] of [['start',{}],['set_position',{point:origin}]].entries())s=applyLocalCommand(s,{v:1,semantics:2,id:'seed'+i,at:'2026-01-01T00:00:00Z',expected_revision:i,command,data});return s;};
 try{
  globalThis.fetch=async()=>{requests++;const raw=JSON.stringify(active.pack),sha=await hash(raw);return new Response(JSON.stringify({offline:{lease_id:active.pack.round.id,round_id:active.pack.round.id,device_id:'device-one',sha256:sha,base_version:0,cursor:2,status:'active'},offline_state:stateFor(active),offline_package:{package:active.pack,payload_json:raw,sha256:sha,source_version:0}}),{status:200});};
  const local=new OfflineRound('https://example.test','token',store,'a',()=> 'device-one',hash);await local.prepare(0);const first=await local.strategy();assert.ok(first.options.length);await local.strategy();assert.equal(requests,1);
  active=b;await local.prepare(0);const second=await local.strategy();assert.ok(second.options[0].remaining_yards>first.options[0].remaining_yards+90);
  globalThis.fetch=async()=>{throw Error('no network after preparation');};
  const selected=await local.turn(second.options[0].club,'selected','2026-01-01T00:00:02Z');assert.deepEqual(selected.local_state.selection.target,second.options[0].aim_point);assert.equal(selected.local_state.holes['1'].rows.length,0);
  await local.turn('记录已击球','shot','2026-01-01T00:00:03Z');const following=await local.strategy();assert.equal(following.question,'position');
 }finally{globalThis.fetch=previous;}
});

test('mapped OB or water asks for confirmation without inventing a penalty and respects an in-bounds report',()=>{
 const f=approach(fixture({greenAt:200,zones:[rect('water','water',-10,-10,10,10)]}));f.model.holes['1'].rows[0].id='shot';
 const r=planStrategy(f.pack,f.model);assert.equal(r.question,'ball_outcome');assert.equal(r.suspected,'possible_water');assert.equal(f.model.pending,null);
 f.model.holes['1'].rows[0].boundary_confirmation={result:'in_bounds',position:{...origin}};assert.notEqual(planStrategy(f.pack,f.model).question,'ball_outcome');
 f.model.holes['1'].rows[0].boundary_confirmation=null;f.model.holes['1'].incidents=[{stroke_id:'shot',cause:'water'}];assert.equal(planStrategy(f.pack,f.model).question,'position');
});
test('a finder with a reported Carry produces two typed facts and never records a stroke',async()=>{
 const {parseLocalTurn}=await import('../shared/core/dialogue.ts');const f=fixture();const turn=parseLocalTurn(f.model,'保底球杆5号木200码');assert.equal(turn.commands.length,2);let state=f.model;
 for(const [n,cmd] of turn.commands.entries())state=applyLocalCommand(state,{v:1,semantics:2,id:'finder'+n,at:'2026-01-01T00:00:00Z',expected_revision:state.revision,...cmd});
 assert.equal(bag(state.profile).find(c=>c.label==='5号木').high,200);assert.equal(state.profile.fairway_finder.value.club,'5号木');assert.equal(state.holes['1'].rows.length,0);
});

test('a configured finder with unknown Carry is requested instead of being silently replaced by an estimated iron',()=>{
 const f=fixture();delete f.model.profile.five_wood;const r=planStrategy(f.pack,f.model,{kind:'conservative'});assert.equal(r.question,'finder_carry');assert.equal(r.missing_club,'5号木');assert.equal(r.options.length,0);
});

test('one historical miss is only reference while repeated misses can change the default club without narration',()=>{
 const f=fixture();const shot={id:'old1',round_id:'previous1',club:'一号木',origin,landing:point(0,260),hazards:['ob']};
 f.pack.history_by_hole={'1':[shot]};assert.equal(planStrategy(f.pack,f.model).options[0].club,'一号木');
 f.pack.history_by_hole['1'].push({...shot,id:'old2',round_id:'previous2'});const r=planStrategy(f.pack,f.model);assert.notEqual(r.options[0].club,'一号木');assert.doesNotMatch(r.text,/历史参考|上次|之前.*记录/);
});

test('explicit demo OB segments stop at their endpoints and do not turn the hole outline into OB',async()=>{
 const {boundaryRisk}=await import('../shared/core/geometry.ts');const h={boundary_segments:[{kind:'ob',a:point(10,0),b:point(10,100),inside_reference:point(0,50),source:'test-stakes',simulation_only:true}]};
 assert.equal(boundaryRisk(h,point(20,50),true),'ob');assert.equal(boundaryRisk(h,point(20,110),true),null);assert.equal(boundaryRisk(h,point(0,50),true),null);assert.equal(boundaryRisk(h,point(20,50),false),null);assert.equal(boundaryRisk({simulation_boundary_rings:[]},point(20,50),true),null);
});

function narrowLanding(angle){
 const f=fixture({driver:240,wood:240,greenAt:380});
 f.pack.profile=f.model.profile={driver:reported(240)};
 const x=Math.sin(angle*Math.PI/180)*240,y=Math.cos(angle*Math.PI/180)*240;
 f.hole.surface_zones=[rect('narrow','fairway',x-2,y-4,x+2,y+4),rect('green','green',-12,370,12,390)];
 return f;
}
test('mapped narrow tee landing arcs between grid angles are found on either side',()=>{
 for(const angle of [-4.5,-3,-1,1.75,3,4.5]){
  const f=narrowLanding(angle),r=planStrategy(f.pack,f.model);
  assert.equal(r.options.length,1,'angle '+angle);assert.equal(r.options[0].club,'一号木');assert.equal(r.options[0].carry_yards,240);
  assert.ok(surfaces(f.hole,false).some(s=>s.kind==='fairway'&&contains(s,r.options[0].landing_point)));
 }
});
test('narrow off-reference green landings and roll-in entries are refined without inventing Carry',()=>{
 for(const roll of [false,true]){
  const f=approach(fixture({greenAt:roll?240:180})),left=roll?9:7,bottom=roll?216:152,top=roll?246:190,join=roll?236:175,right=roll?15:13;
  f.pack.profile=f.model.profile={bag_overrides:{[roll?'3号木':'7号铁']:{low:roll?210:160,high:roll?210:160}}};
  const outline=[[left,bottom],[right,bottom],[right,top],[-5,top],[-5,join],[left,join],[left,bottom]].map(([x,y])=>{const p=point(x,y);return [p.longitude,p.latitude]});
  f.hole.surface_zones=[rect('fairway','fairway',-35,1,35,top),{id:'green',surface:'green',verified:true,source:'test',geometry:{type:'Polygon',coordinates:[outline]}}];
  const r=planStrategy(f.pack,f.model),attack=r.options.find(o=>o.target_surface==='green');assert.ok(attack);assert.equal(attack.carry_yards,roll?210:160);
  assert.ok(surfaces(f.hole,false).some(s=>s.kind==='green'&&contains(s,attack.aim_point)));
  if(roll)assert.ok(attack.roll_yards>0&&attack.roll_yards<=10);
 }
});
test('refined narrow landings still reject mapped water and explicit OB',()=>{
 for(const kind of ['water','ob']){
  const f=narrowLanding(3),x=Math.sin(3*Math.PI/180)*240,y=Math.cos(3*Math.PI/180)*240;
  if(kind==='water')f.hole.surface_zones.push(rect('water','water',x-3,y-5,x+3,y+5));
  else f.hole.boundary_segments=[{kind:'ob',source:'verified-test',a:point(x-3,y-10),b:point(x-3,y+10),inside_reference:point(0,0)}];
  assert.equal(planStrategy(f.pack,f.model).options.length,0,kind);
 }
});
test('fragmented maps keep angular refinement bounded and polygon holes remain excluded',()=>{
 const f=narrowLanding(3),zones=[];
 for(let n=0;n<120;n++){const angle=(-47+n*.78)*Math.PI/180,x=Math.sin(angle)*240,y=Math.cos(angle)*240;zones.push(rect('island'+n,'fairway',x-.15,y-.15,x+.15,y+.15));}
 f.hole.surface_zones=zones;const all=surfaces(f.hole,false),offsets=landingOffsets(all,origin,0,'fairway');assert.ok(offsets(240*YARD).length<=64);
 const hole=narrowLanding(3),surface=hole.hole.surface_zones[0],ring=surface.geometry.coordinates[0];
 surface.geometry.coordinates.push(ring.map(([x,y])=>{const cx=ring.slice(0,-1).reduce((sum,v)=>sum+v[0],0)/4,cy=ring.slice(0,-1).reduce((sum,v)=>sum+v[1],0)/4;return [cx+(x-cx)*.75,cy+(y-cy)*.75];}));
 const plan=planStrategy(hole.pack,hole.model);for(const row of plan.options)assert.ok(surfaces(hole.hole,false).some(s=>s.kind==='fairway'&&contains(s,row.landing_point)));
});
test('roll-in strategies reject thin water and OB beyond an otherwise valid Carry landing',()=>{
 for(const kind of ['water','ob']){
  const f=approach(fixture({greenAt:250,greenDepth:8,greenWidth:8,wood:240}));
  if(kind==='water')f.hole.surface_zones.push(rect('thin-water','water',-45,244.2,45,244.4));
  else f.hole.boundary_segments=[{kind:'ob',source:'test',a:point(-5,242),b:point(-5,260),inside_reference:point(-10,240)}];
  const result=planStrategy(f.pack,f.model);
  assert.ok(!result.options.some(o=>o.club==='3号木'&&o.roll_yards>0),kind);
 }
});
test('invalid historical distances do not become repeated-miss penalties in the shared strategy',()=>{
 const f=fixture({driver:240});
 const shot={id:'old',round_id:'previous',club:'一号木',origin:point(0,0),landing:point(0,240),hazards:['ob'],distance_valid:false};
 f.pack.history_by_hole={'1':[shot,{...shot,id:'old2',round_id:'previous2'}]};
 const result=planStrategy(f.pack,f.model);
 assert.equal(result.options[0].club,'一号木');assert.equal(result.options[0].history_weight,0);
});
