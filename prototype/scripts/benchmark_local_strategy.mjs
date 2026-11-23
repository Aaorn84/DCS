import {CORE_VERSION,CORE_DATASET} from '../shared/core/protocol.ts';
import fs from 'node:fs';import {performance} from 'node:perf_hooks';import {createHash} from 'node:crypto';
import {planStrategy} from '../shared/core/strategy.ts';import {createLocalRound} from '../shared/core/roundEngine.ts';import {OfflineRound} from '../apps/mobile/src/offlineRound.ts';
const raw=fs.readFileSync(new URL('../services/api/assets/phoenix-demo.json',import.meta.url),'utf8'),course=JSON.parse(raw);
const value=distance=>({value:{distance,distance_type:'carry',units:'码'}}),profile={driver:value(260),three_wood:value(240),five_wood:value(220),seven:value(160)};
const packFor=course=>({schema:1,core_version:CORE_VERSION,dataset:CORE_DATASET,local_command_semantics:2,local_rules_version:1,round:{id:'r',tee:'蓝Tee',start_hole:1},course,profile});
const modelFor=(pack,hole)=>{const model=createLocalRound(pack);model.stage='playing';model.hole=hole.number;model.position=hole.simulation_positions.tee;return model;};
const cold=[],warm=[];const numbers=course.holes.filter(h=>h.par>=4).map(h=>h.number);
for(let repeat=0;repeat<5;repeat++)for(const number of numbers){let start=performance.now();const decoded=JSON.parse(raw),pack=packFor(decoded);planStrategy(pack,modelFor(pack,decoded.holes[number-1]));cold.push(performance.now()-start);const hotPack=packFor(course);start=performance.now();planStrategy(hotPack,modelFor(hotPack,course.holes[number-1]));warm.push(performance.now()-start);}
const hash=async s=>createHash('sha256').update(s).digest('hex'),rows=new Map(),store={getItem:async k=>rows.get(k)??null,setItem:async(k,v)=>rows.set(k,v)},pack=packFor(course),payload_json=JSON.stringify(pack),sha256=await hash(payload_json),previous=globalThis.fetch;
const local=new OfflineRound('https://offline.invalid','token',store,'a',()=> 'device-one',hash),hits=[];
try{
 globalThis.fetch=async()=>new Response(JSON.stringify({offline:{lease_id:'l',round_id:'r',device_id:'device-one',sha256,base_version:0,cursor:0,status:'active'},offline_package:{package:pack,payload_json,sha256,source_version:0}}),{status:200});
 await local.prepare(0);globalThis.fetch=async()=>{throw Error('network disabled');};await local.turn('开始球局','start','2026-01-01T00:00:00Z');await local.execute('set_position',{point:course.holes[0].simulation_positions.tee},'position','2026-01-01T00:00:01Z');await local.strategy();
 for(let n=0;n<100;n++){const start=performance.now();await local.strategy();hits.push(performance.now()-start);}
}finally{globalThis.fetch=previous;}
const stats=s=>{const a=[...s].sort((a,b)=>a-b);return {samples:a.length,p50_ms:Number(a[Math.floor(a.length*.5)].toFixed(3)),p95_ms:Number(a[Math.floor(a.length*.95)].toFixed(3)),max_ms:Number(a.at(-1).toFixed(3))};};
console.log(JSON.stringify({environment:{host:process.platform+' '+process.arch,node:process.version,scope:'Phoenix par4/5 tees; 5 repetitions. Cold includes JSON decode and model construction, not disk/app startup. No native voice/GPS timing.'},cold_input:stats(cold),warm_geometry:stats(warm),unchanged_plan_cache:stats(hits)},null,2));
