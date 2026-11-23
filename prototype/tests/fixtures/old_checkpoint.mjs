import {createHash,randomUUID} from 'node:crypto';
import {coreFor} from '../../shared/core/runtime.ts';
import {CORE_DATASET} from '../../shared/core/protocol.ts';
import {savePackage} from '../../apps/mobile/src/immutablePackage.ts';
import {encodeLocalState} from '../../apps/mobile/src/localStateCodec.ts';
import {CheckpointStore} from '../../apps/mobile/src/checkpointStore.ts';
const hash=async s=>createHash('sha256').update(s).digest('hex');
export async function oldCheckpoint(input={}){
 const rawRows=new Map(),raw={getItem:async k=>rawRows.get(k)??null,setItem:async(k,v)=>rawRows.set(k,v),removeItem:async k=>rawRows.delete(k)};
 const store=new CheckpointStore(raw,hash,k=>!k.includes('.package.'));const engine=coreFor(input.core_version??'1.4.0');
 const asset=input.asset??{schema:1,core_version:engine.version,dataset:CORE_DATASET,tees:['蓝Tee'],course:{course_id:'course',map_version:'old-map',crs:'WGS84',holes:Array.from({length:18},(_,i)=>({number:i+1,par:4,objects:[]}))}};
 const round={id:randomUUID(),course:asset.course.course_id,tee:'蓝Tee',start_hole:1,started_at:new Date().toISOString()},setup={memory_allowed:true,patch:{carries:{'一号木':{low:260,high:260},'7号铁':{low:160,high:160}}}};
 const pack=engine.assembleOfflinePackage(asset,input.context??{},setup,round),payload_json=engine.canonicalJson(pack),digest=await hash(payload_json),envelope={package:pack,payload_json,sha256:digest,source_version:0};
 let state=engine.createLocalRound(pack),next=1;const queue=[];
 const apply=(command,data={})=>{const event={v:1,semantics:2,id:'old-'+next,at:round.started_at,expected_revision:state.revision,command,data};state=engine.applyLocalCommand(state,event);queue.push({seq:next++,event:{type:'local_round_command',event_id:event.id,observed_at:event.at,data:event}});};
 apply('start');for(let hole=1;hole<=9;hole++){apply('select_club',{club:'一号木'});apply('record_stroke');apply('draft_score',{total:4,putts:2,penalties:0});apply('confirm_score',{confirmed:true});apply('switch_hole',{hole:hole+1});}
 const key='account-a.round.'+round.id,device_id='device-'+randomUUID();await savePackage(store,key+'.package.'+digest,envelope);
 const disk={schema:1,device_id,package_ref:digest,package_source_version:0,local_state:encodeLocalState(state),next,queue,lease:{lease_id:'unregistered-'+round.id,round_id:round.id,device_id,sha256:digest,base_version:0,cursor:0,status:'active'},native_start:{registered:false,registration:{round_id:round.id,device_id,core_version:engine.version,asset_sha256:input.asset_sha256??'a'.repeat(64),context_sha256:input.context_sha256??'b'.repeat(64),round,setup,package_sha256:digest}}};
 await store.setItem(key,JSON.stringify(disk));return {store,rawRows,key,state,disk,envelope,round,asset};
}
