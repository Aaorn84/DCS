import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const script=fs.readFileSync(new URL('../../demo-local/index.html',import.meta.url),'utf8').split('<script>')[1].split('</script>')[0];
const state={stage:'active',version:21,round:null,quiet:false,profile:{},history:[],memory_allowed:false,coach:{enabled:false},distance_unit:'码',score_summary:{confirmed_holes:0},choices:[]};
function setup(fetcher){
 const nodes=new Map();let id=0;
 const element=()=>({value:'',textContent:'',hidden:false,dataset:{},setAttribute(){},children:[],get options(){return this.children},append(x){this.children.push(x)},replaceChildren(){this.children=[]}});
 const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
 const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[],createElement:element,createElementNS:element,addEventListener(){}},window:{addEventListener(){}},cancelAnimationFrame(){},fetch:fetcher,AbortController,setTimeout,clearTimeout,setInterval:()=>0,crypto:{randomUUID:()=>`op-${++id}`}});
 vm.runInContext(script,context);vm.runInContext(`token='test';journey=${JSON.stringify(state)}`,context);
 return {context,get,submit:()=>get('form').onsubmit({preventDefault(){}}),value:expr=>vm.runInContext(expr,context)};
}
function reply(status=200,current=state){return {ok:status===200,status,json:async()=>status===200?{journey:{...state,version:22},result:{text:'已给出方案。'}}:{error:'version conflict',current}}}
test('lost reply retains answer and retries the identical operation without duplicate user bubble',async()=>{
 const requests=[];let attempt=0;const ui=setup(async(path,options)=>{requests.push(JSON.parse(options.body));if(!attempt++)throw new TypeError('Failed to fetch');return reply()});
 ui.get('utterance').value='190';await ui.submit();assert.equal(ui.get('utterance').value,'190');assert.equal(ui.get('retryInline').hidden,false);assert.match(ui.get('sendStatus').textContent,/已保留/);
 await ui.get('retryInline').onclick();assert.deepEqual(requests[0],requests[1]);assert.equal(ui.get('utterance').value,'');assert.equal(ui.get('sendStatus').textContent,'');assert.equal(ui.get('retryInline').hidden,true);assert.equal(ui.get('chat').children.filter(x=>x.textContent==='你：190').length,1);
});
test('submission while background GPS is busy never clears the draft or sends it into another request',async()=>{
 let calls=0;const ui=setup(async()=>{calls++;return reply()});ui.get('utterance').value='190';vm.runInContext('busy=true',ui.context);await ui.submit();assert.equal(calls,0);assert.equal(ui.get('utterance').value,'190');assert.match(ui.get('sendStatus').textContent,/输入已保留/);
});
test('a state conflict refreshes displayed state but preserves the unsent answer for user review',async()=>{
 const ui=setup(async()=>reply(409,{...state,version:25}));ui.get('utterance').value='190';await ui.submit();assert.equal(ui.get('utterance').value,'190');assert.equal(ui.value('journey.version'),25);assert.equal(ui.value('pending'),null);assert.match(ui.get('sendStatus').textContent,/核对当前问题/);
});
test('an acknowledgement cannot erase a newer draft typed while a request was in flight',async()=>{
 let acknowledge;const ui=setup(()=>new Promise(resolve=>acknowledge=resolve));ui.get('utterance').value='190';const sent=ui.submit();ui.get('utterance').value='我想用一号木';acknowledge(reply());await sent;assert.equal(ui.get('utterance').value,'我想用一号木');
});

const map={hole:1,source_name:'A1',par:4,published_yardage:360,bounds:[114,22,114.002,22.004],paths:[],positions:{tee:{latitude:22,longitude:114},green:{latitude:22.004,longitude:114.002}}};
test('projection roundtrip and selection preview never send GPS until confirmed',async()=>{let calls=0;const ui=setup(async()=>{calls++;return {ok:true,json:async()=>({journey:{...state,simulation:map},result:{text:''}})}});ui.value(`journey.simulation=${JSON.stringify(map)}`);const p={latitude:22.002,longitude:114.001};const xy=ui.value(`mapProjection(journey.simulation.bounds).toPoint(${JSON.stringify(p)})`);ui.value(`selectMapPoint(${xy[0]},${xy[1]})`);assert.equal(calls,0);assert.ok(Math.abs(ui.value('selectedMapPosition.latitude')-p.latitude)<1e-10);assert.match(ui.get('mapSelection').textContent,/待提交/);await ui.get('mapSubmit').onclick();assert.equal(calls,1);assert.equal(ui.value('activeSimulation'),'map');assert.equal(ui.value('selectedMapPosition'),null);assert.equal(ui.value("simPosition('map').latitude"),p.latitude)});
test('rejected GPS retains preview and does not activate selected position',async()=>{const ui=setup(async()=>({ok:true,json:async()=>({journey:{...state,simulation:map},result:{ignored:true,reason:'implausible_jump'}})}));ui.value(`journey.simulation=${JSON.stringify(map)};selectMapPoint(250,250)`);await ui.get('mapSubmit').onclick();assert.equal(ui.value('acceptedMapPosition'),null);assert.notEqual(ui.value('selectedMapPosition'),null);assert.equal(ui.value('activeSimulation'),null)});
test('off-map clicks and stages without a selected course cannot create a position',()=>{const ui=setup();ui.value(`journey.simulation=${JSON.stringify(map)}`);assert.equal(ui.value('selectMapPoint(-100,-100)'),false);ui.value("journey.stage='ready'");assert.equal(ui.value('selectMapPoint(250,250)'),true);ui.value("journey.stage='course'");assert.equal(ui.value('selectMapPoint(250,250)'),false)});

test('club groups follow the current hole and preserve manual toggles during refresh',()=>{
 const ui=setup(async()=>reply());
 const j={...state,round:{id:'r',start_hole:3},current_hole:3,round_records:{clubs:[{hole:3,club:'一号木'},{hole:4,club:'7号铁'}]}};
 ui.value(`renderRoundRecords(${JSON.stringify(j)})`);
 assert.equal(ui.get('clubGroups').children[0].open,true);
 assert.equal(ui.get('clubGroups').children[1].open,false);
 ui.get('clubGroups').children[0].open=false;
 ui.value(`renderRoundRecords(${JSON.stringify(j)})`);
 assert.equal(ui.get('clubGroups').children[0].open,false);
 j.current_hole=4;ui.value(`renderRoundRecords(${JSON.stringify(j)})`);
 assert.equal(ui.get('clubGroups').children[0].open,false);
 assert.equal(ui.get('clubGroups').children[1].open,true);
});
test('known carry panel uses reported ranges and converts units',()=>{
 const ui=setup(async()=>reply());
 const j={...state,distance_unit:'米',profile:{seven:{value:{distance:160,units:'码',distance_type:'carry'}},driver:{value:{distance:260,units:'码',distance_type:'total'}},lofted_wedge_ranges:{value:{52:{low:0,high:85,units:'码'}}}}};
 ui.value(`renderCarry(${JSON.stringify(j)})`);
 const rows=ui.get('carryRows').children;
 assert.equal(rows.length,2);
 assert.equal(rows[0].children[0].textContent,'7号铁');assert.equal(rows[0].children[1].textContent,'146米');
 assert.equal(rows[1].children[1].textContent,'0–78米');
});
test('position update and simulated stroke use separate explicit actions',async()=>{
 const requests=[];const ui=setup(async(path,options)=>{requests.push(JSON.parse(options.body));return reply()});
 ui.value(`journey.simulation=${JSON.stringify(map)};selectMapPoint(250,250)`);
 await ui.get('mapSubmit').onclick();assert.equal(requests[0].event.data.simulation_position_action,'move');
 ui.value(`journey.simulation=${JSON.stringify(map)};selectMapPoint(260,260)`);
 await ui.get('mapShot').onclick();assert.equal(requests[1].event.data.simulation_position_action,'shot');
});
test('login restore resumes saved simulation and refreshes it before a late answer',async()=>{
 const requests=[];const ui=setup(async(path,options)=>{requests.push(JSON.parse(options.body));return reply()});
 const saved={...state,simulation:{...map,device_position:{latitude:31,longitude:121,accuracy_m:2,simulation_source:'map_click',simulation_hole:map.hole,observed_at:new Date(Date.now()-76000).toISOString()}}};
 ui.value(`journey=${JSON.stringify(saved)};restoreSimulation(journey)`);
 assert.equal(ui.value('activeSimulation'),'map');
 ui.get('utterance').value='一号木';await ui.submit();
 assert.deepEqual(requests.map(r=>r.event.type),['gps','message']);
 assert.equal(requests[0].event.data.simulation_refresh,true);
 assert.equal(requests[1].event.text,'一号木');
});
test('restore does not invent simulation positions for real GPS',()=>{
 const ui=setup(async()=>reply());
 assert.equal(ui.value(`restoreSimulation(${JSON.stringify({...state,simulation:{...map,device_position:{latitude:31,longitude:121,simulation_hole:map.hole}}})})`),false);
 assert.equal(ui.value('activeSimulation'),null);
});
test('same-hole reset replaces cached old landing with the reset tee position',()=>{
 const ui=setup(async()=>reply());
 const base={...state,round:{id:'r'},simulation:{...map,attempt:'old',device_position:{...map.positions.green,accuracy_m:2,simulation_source:'map_click',simulation_hole:map.hole}}};
 ui.value(`render(${JSON.stringify(base)});restoreSimulation(journey)`);
 base.simulation.attempt='new';base.simulation.device_position={...map.positions.tee,accuracy_m:2,simulation_source:'map_click',simulation_hole:map.hole};
 ui.value(`render(${JSON.stringify(base)})`);
 assert.equal(ui.value('acceptedMapPosition.latitude'),map.positions.tee.latitude);
 assert.equal(ui.value('acceptedMapPosition.longitude'),map.positions.tee.longitude);
 assert.equal(ui.value('selectedMapPosition'),null);
});

test('score totals separate front back and whole round without adding penalties twice',()=>{
 const ui=setup();
 const scores=[{hole:1,total:5,putts:2,penalties:1},{hole:9,total:4,putts:1,penalties:0},{hole:10,total:6,putts:2,penalties:2},{hole:18,total:5,putts:2,penalties:0}];
 ui.value(`renderRoundRecords(${JSON.stringify({...state,round:{id:'r'},score_summary:{scores}})})`);
 const cols=ui.value(`scorecardColumns(${JSON.stringify(scores)}).filter(c=>c.summary)`);
 assert.equal(JSON.stringify(cols.map(c=>[c.label,c.count,c.total,c.putts,c.penalties])),JSON.stringify([['前九',2,'9','3','1'],['后九',2,'11','4','2'],['总计',4,'20','7','3']]));
 assert.equal(ui.get('scoreHead').children[0].children.length,22);
 const cell=ui.get('scoreRows').children[0].children[1];
 const box=cell.children[0];assert.equal(box.children[0].textContent,5);
 assert.equal(box.children[1].className,'scorecard-penalty');assert.equal(box.children[1].textContent,1);
 assert.equal(box.children[2].className,'scorecard-putts');assert.equal(box.children[2].textContent,2);
});
test('score totals omit drafts and keep unknown putts visible',()=>{
 const ui=setup();
 const scores=[{hole:1,total:4,putts:2,penalties:0},{hole:2,total:5,putts:null,penalties:null}];
 const j={...state,round:{id:'r'},score_summary:{scores},round_records:{score_draft:{hole:3,total:7,putts:3,penalties:1}}};
 ui.value(`renderRoundRecords(${JSON.stringify(j)})`);
 const cols=ui.value(`scorecardColumns(${JSON.stringify(scores)}).filter(c=>c.summary)`);
 assert.equal(JSON.stringify(cols.map(c=>[c.label,c.count,c.total,c.putts,c.penalties])),JSON.stringify([['前九',2,'9','2*','0*'],['后九',0,null,null,null],['总计',2,'9','2*','0*']]));
 assert.equal(ui.get('scoreRows').children[0].children[3].children[0].children[0].textContent,'—');
});

test('postgame highlights chat does not send a stale simulation GPS first',async()=>{
 const requests=[];const ui=setup(async(path,options)=>{requests.push(JSON.parse(options.body));return reply()});
 ui.value(`journey=${JSON.stringify({...state,stage:'postgame',round:{id:'r'},simulation:{...map,device_position:{observed_at:'2020-01-01T00:00:00Z'}}})};activeSimulation='map';acceptedMapPosition={latitude:22,longitude:114}`);
 ui.get('utterance').value='聊聊高光';await ui.submit();
 assert.equal(requests.length,1);assert.equal(requests[0].event.type,'message');assert.equal(requests[0].event.text,'聊聊高光');
});
test('rendering postgame stops lingering simulation and preserves scorecard',()=>{
 const ui=setup();ui.value("activeSimulation='map';lastSimulation='map';acceptedMapPosition={latitude:22,longitude:114}");
 ui.value(`render(${JSON.stringify({...state,stage:'postgame',round:{id:'r'},simulation:map,score_summary:{scores:[{hole:18,total:5,putts:2,penalties:0}]}})})`);
 assert.equal(ui.value('activeSimulation'),null);assert.equal(ui.value('lastSimulation'),null);assert.equal(ui.get('recordsCard').hidden,false);
});

test('round review details stay folded until explicitly requested and preserve manual collapse',()=>{
 const ui=setup();const review={round_id:'r',summary:'今天82杆。',details:'详细统计',expand_event:null};const j={...state,round:{id:'r'},round_review:review};
 ui.value(`renderRoundRecords(${JSON.stringify(j)})`);assert.equal(ui.get('roundReview').hidden,false);assert.equal(ui.get('roundAnalysis').open,false);
 review.expand_event='open-1';ui.value(`renderRoundRecords(${JSON.stringify(j)})`);assert.equal(ui.get('roundAnalysis').open,true);
 ui.get('roundAnalysis').open=false;ui.value(`renderRoundRecords(${JSON.stringify(j)})`);assert.equal(ui.get('roundAnalysis').open,false);
 assert.equal(ui.get('roundAnalysisText').textContent,'详细统计');
});

test('history detail loading is explicit and requests only the selected hole',async()=>{
 const requests=[];const ui=setup(async(path,options)=>{const body=JSON.parse(options.body);requests.push(body);return {ok:true,json:async()=>body.action==='history'?{history_page:{rounds:[{round:{id:'old',tee:'蓝Tee'},confirmed_holes:18,confirmed_subtotal:80}],total:1,offset:0,has_more:false}}:{history_hole:{hole:5,score:{total:6,putts:2,penalties:0},shots:[{stroke_number:3,club:'P杆',distance_m:100,hazards:[]}]}}}});
 assert.equal(requests.length,0);await ui.get('loadHistory').onclick();assert.equal(requests[0].action,'history');
 ui.get('historyRound').value='old';ui.get('historyHole').value='5';await ui.get('readHistoryHole').onclick();assert.deepEqual(requests[1],{action:'history_hole',round_id:'old',hole:5});assert.match(ui.get('historyHoleDetails').textContent,/P杆/);
});

test('compact replies restore unchanged sections and reset across accounts',async()=>{
 let n=0;const app=setup(async()=>({ok:true,status:200,json:async()=>++n===1?{journey:{...state,profile:{name:'A'}},journey_revisions:{profile:'hash'}}:{journey:{...state,profile:undefined},journey_revisions:{profile:'hash'},journey_unchanged:['profile']}}));
 await app.value("api('/journey',{action:'event'})");
 const d=await app.value("api('/journey',{action:'event'})");assert.equal(d.journey.profile.name,'A');
 app.value("token='another';");await assert.rejects(app.value("api('/journey',{action:'event'})"),/缓存失效/);
});
test('map outlines survive device marker updates and redraw when geometry changes',()=>{
 const app=setup();const j={...state,simulation:{hole:1,bounds:[0,0,1,1],paths:[],positions:{tee:{latitude:.1,longitude:.1},green:{latitude:.9,longitude:.9}},device_position:{latitude:.2,longitude:.2}}};
 app.value(`renderMap(${JSON.stringify(j)})`);const layer=app.get('courseMap').markerLayer;
 j.simulation.device_position.latitude=.3;app.value(`renderMap(${JSON.stringify(j)})`);assert.equal(app.get('courseMap').markerLayer,layer);
 j.simulation.paths=[{kind:'FairwayTrace',points:[{latitude:0,longitude:0},{latitude:1,longitude:1}]}];app.value(`renderMap(${JSON.stringify(j)})`);assert.notEqual(app.get('courseMap').markerLayer,layer);
});
test('unchanged simulated position skips background refresh but retains freshness heartbeat',()=>{
 const app=setup();app.value("journey.simulation={hole:1,positions:{tee:{latitude:31,longitude:120.9992,accuracy_m:2}}};activeSimulation='tee';lastSimulationRefresh=null");assert.equal(app.value('needsSimulationRefresh()'),true);
 app.value("lastSimulationRefresh={key:JSON.stringify([journey?.round?.id,journey?.simulation?.hole,journey?.simulation?.attempt,31,120.9992,2]),at:Date.now()}");
 assert.equal(app.value('needsSimulationRefresh()'),false);app.value('lastSimulationRefresh.at-=46000');assert.equal(app.value('needsSimulationRefresh()'),true);
});

test('the webpage sends playing events to the shared core entry and displays its authoritative bag',async()=>{
 const requests=[];const ui=setup(async(_path,options)=>{requests.push(JSON.parse(options.body));return reply()});ui.get('utterance').value='7号铁';await ui.submit();assert.equal(requests[0].action,'core_event');
 ui.value(`renderCarry(${JSON.stringify({...state,profile:{three_wood:{value:{distance:240,distance_type:'carry',units:'码'}}},core_carry:[{label:'3号木',low:210,high:210,estimated:false},{label:'52度杆',low:0,high:85,estimated:false}]})})`);
 assert.equal(ui.get('carryRows').children[0].children[1].textContent,'210码');assert.equal(ui.get('carryRows').children[1].children[1].textContent,'0–85码');
});
test('missing map positions cannot fall back to retired synthetic coordinates',()=>{
 const ui=setup();ui.value("journey={stage:'active',round:{start_hole:2}};");assert.throws(()=>ui.value("simPosition('tee')"),/缺少该模拟位置/);
});
test('temporary HTTP errors keep the answer, retry button and identical web envelope',async()=>{
 for(const status of [408,425,429,500,502,503,504]){
  const requests=[];let attempts=0;const ui=setup(async(_path,options)=>{requests.push(options.body);return reply(attempts++?200:status)});
  ui.get('utterance').value='确认记录';await ui.submit();assert.ok(ui.value('pending'),status);assert.equal(ui.get('retryInline').hidden,false);assert.match(ui.get('sendStatus').textContent,/已保留/);
  await ui.get('retryInline').onclick();assert.equal(requests[0],requests[1]);assert.equal(ui.value('pending'),null);assert.equal(ui.get('utterance').value,'');
 }
});
