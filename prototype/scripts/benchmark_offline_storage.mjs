import {CORE_VERSION,CORE_DATASET} from '../shared/core/protocol.ts';
// Host-only storage comparison; not a measurement of native ASR/TTS or AsyncStorage.
import {mkdtempSync,rmSync,readdirSync,statSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {performance} from 'node:perf_hooks';
import {diskStore,hash} from '../tests/fixtures/offline_disk_worker.mjs';
import {CheckpointStore} from '../apps/mobile/src/checkpointStore.ts';
import {OfflineRound} from '../apps/mobile/src/offlineRound.ts';
const repeats=Number(process.argv[2]??5);
if(!Number.isSafeInteger(repeats)||repeats<1||repeats>30)throw Error('repeats must be 1..30');
const pack={schema:1,local_rules_version:1,dataset:CORE_DATASET,local_command_semantics:2,core_version:CORE_VERSION,round:{id:'r',tee:'蓝Tee',start_hole:1},course:{course_id:'c',geometry:'x'.repeat(100000),holes:Array.from({length:18},(_,i)=>({number:i+1,par:4}))}};
const raw=JSON.stringify(pack),sha=await hash(raw),previous=globalThis.fetch;
const percentile=(xs,p)=>Number([...xs].sort((a,b)=>a-b)[Math.min(xs.length-1,Math.ceil(xs.length*p)-1)].toFixed(3));
const results=[];
try{
 for(const checkpoint of [false,true]){
  const hot=[],cold=[],sizes=[];let writes=0,writtenBytes=0;
  for(let run=0;run<repeats;run++){
   const directory=mkdtempSync(path.join(tmpdir(),'caddie-storage-bench-'));
   try{
    const file=diskStore(directory);const counted={...file,setItem:async(k,v)=>{writes++;writtenBytes+=Buffer.byteLength(v);return file.setItem(k,v);}};
    const make=()=>new OfflineRound('https://offline.invalid','token',checkpoint?new CheckpointStore(counted,hash,key=>key==='a'):counted,'a',()=> 'device-one',hash);
    let client=make(),id=0;
    globalThis.fetch=async()=>new Response(JSON.stringify({offline:{lease_id:'l',round_id:'r',device_id:'device-one',sha256:sha,base_version:0,cursor:0,status:'active'},offline_package:{package:pack,payload_json:raw,sha256:sha}}),{status:200});
    await client.prepare(0);globalThis.fetch=async()=>{throw Error('network disabled');};
    const turn=async text=>{const start=performance.now();await client.turn(text,'c'+(++id),'2026-01-01T00:00:00Z');hot.push(performance.now()-start);};
    await turn('开始球局');
    for(let hole=1;hole<=18;hole++){
     for(const text of ['7号铁','记录已击球','这洞五杆两推','确认记录'])await turn(text);
     if(hole===1||hole===9||hole===18){client=make();const start=performance.now();await client.verifyCached();cold.push(performance.now()-start);}
     if(hole<18)await turn('下一洞');
    }
    sizes.push(readdirSync(directory).reduce((n,name)=>n+statSync(path.join(directory,name)).size,0));
   }finally{rmSync(directory,{recursive:true,force:true});}
  }
  results.push({mode:checkpoint?'two_slot_checkpoint':'single_document',rounds:repeats,commands:hot.length,command_ms:{p50:percentile(hot,.5),p95:percentile(hot,.95)},cold_restore_samples:cold.length,cold_restore_ms:{p50:percentile(cold,.5),p95:percentile(cold,.95)},mean_final_storage_bytes:Math.round(sizes.reduce((a,b)=>a+b,0)/sizes.length),writes,writtenBytes});
 }
 console.log(JSON.stringify({environment:{platform:process.platform,arch:process.arch,node:process.version,adapter:'host files, fsync + rename; 100KB synthetic map; no native speech or storage timing'},results},null,2));
}finally{globalThis.fetch=previous;}
