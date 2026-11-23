import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createHash,randomUUID} from 'node:crypto';
import {oldCheckpoint} from './old_checkpoint.mjs';
import {OfflineRound} from '../../apps/mobile/src/offlineRound.ts';
import {coreFor} from '../../shared/core/runtime.ts';
const input=JSON.parse(fs.readFileSync(0,'utf8')),hash=async s=>createHash('sha256').update(s).digest('hex');
const f=await oldCheckpoint(input);let local=new OfflineRound(input.base,input.token,f.store,f.key,randomUUID,hash);
await local.verifyCached();if(input.pre_synced)await local.synchronize();
const network=globalThis.fetch;globalThis.fetch=async()=>{throw Error('offline after upgrade')};
local=new OfflineRound(input.base,input.token,f.store,f.key,randomUUID,hash);await local.verifyCached();let n=0;
const execute=(command,data={})=>local.execute(command,data,'upgraded-'+(++n),new Date().toISOString());
for(let hole=10;hole<=18;hole++){
 const point=f.asset.course.holes[hole-1].simulation_positions.tee;
 await execute('set_position',{point});await execute('select_club',{club:'7号铁'});await execute('record_stroke');
 if(hole===10){
  await execute('report_incident',{cause:'possible_ob'});
  local=new OfflineRound(input.base,input.token,f.store,f.key,randomUUID,hash);await local.verifyCached();
  await execute('resolve_ball',{result:'ob'});await local.turn('已回上一杆位置，坐标暂未知','complete-relief',new Date().toISOString());
 }
 await execute('draft_score',{total:hole===10?5:4,putts:2,penalties:hole===10?1:0});await execute('confirm_score',{confirmed:true});
 if(hole<18)await execute('switch_hole',{hole:hole+1});
}
await execute('request_finish');await execute('confirm_finish',{confirmed:true});
const before=await local.cached();globalThis.fetch=network;await local.synchronize();await local.synchronize();await local.release();
const snapshot=await local.snapshot();assert.equal(snapshot.journey.score_summary.confirmed_subtotal,73);
const after=await local.verifyCached();assert.equal(after.local_state.core_version,input.asset.core_version);assert.equal(after.queue.length,0);assert.equal(after.package.sha256,f.envelope.sha256);
console.log(JSON.stringify({round_id:f.round.id,core_version:after.local_state.core_version,totals:coreFor(after.local_state.core_version).localTotals(after.local_state),server_total:snapshot.journey.score_summary.confirmed_subtotal,events:after.next-1}));
