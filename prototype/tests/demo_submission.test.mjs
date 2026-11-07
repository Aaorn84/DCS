import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const script=fs.readFileSync(new URL('../../demo-local/index.html',import.meta.url),'utf8').split('<script>')[1].split('</script>')[0];
const state={stage:'active',version:21,round:null,quiet:false,profile:{},history:[],memory_allowed:false,coach:{enabled:false},distance_unit:'码',score_summary:{confirmed_holes:0},choices:[]};
function setup(fetcher){
 const nodes=new Map();let id=0;
 const element=()=>({value:'',textContent:'',hidden:false,setAttribute(){},children:[],append(x){this.children.push(x)},replaceChildren(){this.children=[]}});
 const get=id=>{if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)};
 const context=vm.createContext({document:{getElementById:get,querySelectorAll:()=>[],createElement:element,createElementNS:element},fetch:fetcher,AbortController,setTimeout,clearTimeout,setInterval:()=>0,crypto:{randomUUID:()=>`op-${++id}`}});
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
