import {coreFor,coreForPackage} from '../../../shared/core/runtime.ts';
import {savePackage,loadPackage,removePackage} from './immutablePackage.ts';
import {CORE_VERSION,CORE_DATASET} from '../../../shared/core/protocol.ts';
import {type PlanIntent} from '../../../shared/core/strategy.ts';
import {encodeLocalState,decodeLocalState,utf8Length} from './localStateCodec.ts';
import {request} from './api.ts';
import type {LocalStore} from './journeyPersistence.ts';
export type OfflineEvent={type:'local_round_command';event_id:string;observed_at:string;data:Record<string,any>};
type Entry={seq:number;event:OfflineEvent};
type Lease={lease_id:string;round_id:string;device_id:string;sha256:string;base_version:number;cursor:number;status:'preparing'|'active'|'released'};
type Disk={schema:1;device_id:string;lease?:Lease;package?:any;package_ref?:string;package_source_version?:number;queue:Entry[];next:number;last_at?:string;local_state?:any;conflict?:string;prepare_intent?:{version:number};clock_warning?:boolean;native_start?:{registration:any;registered:boolean}};
function canonical(value:any):string {if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';return JSON.stringify(value);}
/** Durable shared-core commands, immutable package and verified synchronization. */
export class OfflineRound {
 private disk:Disk|undefined;
 private loading:Promise<Disk>|undefined;
 private tail:Promise<void>=Promise.resolve();
 private syncing=false;
 private generation=0;
 private ackModel:any;
 private advice:any;
 private adviceRevision=-1;
 private adviceScope='';
 private adviceIntent='';
 private packageRef:string|undefined;
 constructor(private base:string,private token:string,private store:LocalStore,private key:string,private newId:()=>string,private sha256:(text:string)=>Promise<string>){}
 private async load():Promise<Disk>{
  if(this.loading)return this.loading;
  if(this.disk)return this.disk;
  const pending=this.readDisk();this.loading=pending;
  try{return await pending;}finally{if(this.loading===pending)this.loading=undefined;}
 }
 private async readDisk(){
  if(!this.disk){
   const raw=await this.store.getItem(this.key);
   if(raw){
    const saved:Disk=JSON.parse(raw);if(saved?.schema!==1)throw Error('离线数据版本不兼容，请保留本机记录。');
    if(saved.package)throw Error('不支持旧内嵌地图存储，请重置过期测试数据。');
    if(saved.package_ref){
     if(!/^[a-f0-9]{64}$/.test(saved.package_ref))throw Error('离线包引用损坏，请保留记录。');
     saved.package=await loadPackage(this.store,this.key+'.package.'+saved.package_ref);if(saved.package_source_version!==undefined)saved.package.source_version=saved.package_source_version;
    }
    if(saved.lease&&!saved.package_ref)throw Error('本机球局缺少地图引用，请保留记录并核对。');
    saved.local_state=decodeLocalState(saved.local_state);this.disk=saved;this.packageRef=saved.package_ref;
   }else{this.disk={schema:1,device_id:this.newId(),queue:[],next:1};await this.save();}
  }
  return this.disk!;
 }
 private async save(){
  try{await this.persistDisk();}catch(error){this.disk=undefined;throw error;}
 }
 private async persistDisk(){
  const disk=this.disk!;const {package:pack,...mutable}=disk;const old=this.packageRef;
  if(pack){
   const digest=pack.sha256;if(!/^[a-f0-9]{64}$/.test(digest))throw Error('离线包摘要无效。');
   if(old!==digest)await savePackage(this.store,this.key+'.package.'+digest,pack);
   mutable.package_ref=digest;mutable.package_source_version=pack.source_version;
  }
  // Only mutable state+queue are committed for each utterance; map bytes stay immutable.
  if(mutable.local_state)mutable.local_state=encodeLocalState(mutable.local_state);
  const serialized=JSON.stringify(mutable);
  if(utf8Length(serialized)>1024*1024)throw Error('本机待同步记录接近容量上限，请先联网同步；原记录未删除。');
  await this.store.setItem(this.key,serialized);
  disk.package_ref=mutable.package_ref;this.packageRef=mutable.package_ref;
  if(old&&old!==this.packageRef&&this.store.removeItem)await removePackage(this.store,this.key+'.package.'+old).catch(()=>{});
 }
 private async exclusive<T>(work:()=>Promise<T>){const previous=this.tail;let done!:()=>void;this.tail=new Promise<void>(resolve=>{done=resolve;});await previous;try{return await work();}finally{done();}}
 async cancelSynchronization(){this.generation++;await this.exclusive(async()=>{});}
 private checkGeneration(value:number){if(value!==this.generation)throw Error('本次后台同步已取消，本机记录保留。');}
 async cached(){const d=await this.load();return JSON.parse(JSON.stringify(d));}
 async verifyCached(){
  const d=await this.load(),pack=d.package;
  const engine=coreForPackage(pack?.package);
  if(!pack||typeof pack.payload_json!=='string'||canonical(JSON.parse(pack.payload_json))!==canonical(pack.package)||await this.sha256(pack.payload_json)!==pack.sha256)throw Error('本机离线包校验失败，请保留数据。');
  if(d.local_state){
   if(!d.lease||d.local_state.round_id!==d.lease.round_id||d.local_state.revision!==d.next-1||d.queue.length!==d.next-d.lease.cursor-1)throw Error('本机离线记录版本不一致，请保留数据。');
   for(const [i,entry] of d.queue.entries())if(entry.seq!==d.lease.cursor+i+1||entry.event.type!=='local_round_command'||canonical(entry.event.data)!==canonical(d.local_state.receipts[entry.event.event_id]))throw Error('本机事件队列不一致，请保留数据。');
   // Rebuild once on cold restoration, never on each spoken turn.
   let rebuilt=engine.createLocalRound(pack.package);const events=Object.values(d.local_state.receipts).sort((a:any,b:any)=>a.expected_revision-b.expected_revision);
   for(const event of events)rebuilt=engine.applyLocalCommand(rebuilt,event as any);
   if(canonical(rebuilt)!==canonical(d.local_state))throw Error('本机球局状态无法由已保存事件重建，请保留数据并核对。');
  }
  return this.cached();
 }
 async beginOffline(spec:any){return this.exclusive(async()=>{
  const d=await this.load();if(d.local_state){if(d.local_state.round_id!==spec.round.id||d.package.sha256!==spec.package.sha256)throw Error('不能覆盖本机已有球局。');if(d.local_state.stage==='ready')await this.applyCommands(d,[{command:'start',data:{}}],'start-'+spec.round.id,spec.round.started_at);return this.cached();}
  const pack=spec.package;if(await this.sha256(pack.payload_json)!==pack.sha256||canonical(JSON.parse(pack.payload_json))!==canonical(pack.package))throw Error('本机开局包校验失败。');
  const model=coreForPackage(pack.package).createLocalRound(pack.package);d.package=pack;d.local_state=model;
  d.lease={lease_id:'unregistered-'+spec.round.id,round_id:spec.round.id,device_id:d.device_id,sha256:pack.sha256,base_version:0,cursor:0,status:'active'};
  d.native_start={registered:false,registration:{round_id:spec.round.id,device_id:d.device_id,core_version:pack.package.core_version,asset_sha256:spec.asset_sha256,context_sha256:spec.context_sha256,round:spec.round,setup:spec.setup,package_sha256:pack.sha256}};
  await this.save();await this.applyCommands(d,[{command:'start',data:{}}],'start-'+spec.round.id,spec.round.started_at);return this.cached();
 });}
 async snapshot(){const d=await this.load();if(d.native_start)return request(this.base,'/offline-rounds',this.token,{action:'snapshot',round_id:d.lease!.round_id,device_id:d.device_id,lease_id:d.lease!.lease_id});throw Error('本机球局不是独立开局。');}
 async download(){return this.exclusive(async()=>{
  if(this.syncing)throw Error('本次同步尚未结束。');const d=await this.load();if(d.lease?.status==='active'||d.lease?.status==='preparing')throw Error('本场离线包已固定，请先完成离线记录。');const pack=await request(this.base,'/journey',this.token,{action:'offline_package'});
  if(typeof pack.payload_json!=='string'||canonical(JSON.parse(pack.payload_json))!==canonical(pack.package)||await this.sha256(pack.payload_json)!==pack.sha256)throw Error('离线资料校验失败。');
  if(pack.package?.core_version!==CORE_VERSION||pack.package?.dataset!==CORE_DATASET||pack.package?.local_command_semantics!==2||pack.package?.local_rules_version!==1)throw Error('离线包核心版本不匹配。');
  d.package=pack;await this.save();return JSON.parse(JSON.stringify(pack));
 });}
 async prepare(version:number){return this.exclusive(async()=>{
  if(this.syncing)throw Error('请等待本次同步结束后再准备球局。');
  const d=await this.load();if(d.queue.length)throw Error('请先同步已有离线记录。');
  try{
   d.prepare_intent={version};await this.save();
   const reply=await request(this.base,'/journey',this.token,{action:'offline_prepare',device_id:d.device_id,expected_version:version,two_phase:true,local_engine_version:1,core_version:CORE_VERSION});
   const raw=reply.offline_package.payload_json;
   if(typeof raw!=='string'||canonical(JSON.parse(raw))!==canonical(reply.offline_package.package))throw Error('离线包内容不一致。');
   const actual=await this.sha256(raw);
   if(actual!==reply.offline_package.sha256||actual!==reply.offline.sha256)throw Error('离线包校验失败，请重新下载；不要删除原记录。');
   coreForPackage(reply.offline_package.package);
   const lease=reply.offline;if(!lease||typeof lease.lease_id!=='string'||typeof lease.round_id!=='string'||!Number.isSafeInteger(lease.base_version)||lease.base_version<0)throw Error('离线准备回执格式错误。');
   this.validateLease(lease,{...lease,device_id:d.device_id,round_id:reply.offline_package.package.round?.id??lease.round_id,sha256:actual,base_version:reply.offline_package.source_version??lease.base_version},0,Number.MAX_SAFE_INTEGER,['preparing','active']);
   if(d.lease?.lease_id!==reply.offline.lease_id){delete d.last_at;delete d.local_state;delete d.conflict;this.ackModel=undefined;}
   if(!d.local_state){if(reply.offline.cursor>0){if(!reply.offline_state)throw Error('缺少已同步的本地规则状态，请保留记录并核对。');d.local_state=reply.offline_state;}else d.local_state=coreForPackage(reply.offline_package.package).createLocalRound(reply.offline_package.package);}
   if(d.local_state&&d.local_state.revision!==reply.offline.cursor)throw Error('本机与服务器准备进度不一致，请保留记录并核对。');
   d.lease=reply.offline;d.package=reply.offline_package;d.next=reply.offline.cursor+1;await this.save();await this.verifyCached();
   if(d.lease?.status==='preparing'){
    const active=await request(this.base,'/journey',this.token,{action:'offline_activate',device_id:d.device_id,lease_id:d.lease.lease_id,sha256:d.lease.sha256});
    this.validateLease(active.offline,d.lease,d.lease.cursor,d.lease.cursor,['active']);d.lease=active.offline;
   }
   delete d.prepare_intent;await this.save();return this.cached();
  }catch(error){this.disk=undefined;throw error;}
 });}
 async recoverPreparation(){const d=await this.load();if(!d.prepare_intent)throw Error('没有待恢复的离线准备。');return this.prepare(d.prepare_intent.version);}
 async cancelPreparation(){return this.exclusive(async()=>{
  if(this.syncing)throw Error('请等待本次同步结束。');const d=await this.load();
  if(d.queue.length||d.lease?.status==='active'&&d.local_state?.revision>0)throw Error('已有本机击球或记分记录，不能取消准备；请先同步。');
  const reply=await request(this.base,'/journey',this.token,{action:'offline_cancel_preparation',device_id:d.device_id,...(d.lease&&d.lease.status!=='released'?{lease_id:d.lease.lease_id}:{})});
  delete d.lease;delete d.local_state;delete d.prepare_intent;delete d.conflict;delete d.last_at;d.next=1;await this.save();return reply;
 });}
 private async applyCommands(d:Disk,commands:{command:string;data:Record<string,any>}[],id:string,at:string){
  if(d.conflict)throw Error(d.conflict);if(d.lease?.status==='released')throw Error('本场已同步结束，当前为只读记录。');if(!d.local_state||d.lease?.status!=='active')throw Error('请先准备本地规则离线球局。');
  const time=Date.parse(at);if(!Number.isFinite(time)||time>Date.now()+300000)throw Error('离线事件时间无效。');
  let model=d.local_state;const entries:Entry[]=[];
  for(const [i,cmd] of commands.entries()){
   const eventId=commands.length===1?id:id+'-'+i;
   const event={v:1 as const,semantics:2 as const,id:eventId,at,expected_revision:model.receipts[eventId]?.expected_revision??model.revision,command:cmd.command,data:JSON.parse(JSON.stringify(cmd.data))};
   const updated=coreFor(model.core_version).applyLocalCommand(model,event);if(updated===model)continue;model=updated;
   entries.push({seq:d.next+entries.length,event:{type:'local_round_command',event_id:event.id,observed_at:at,data:event}});
  }
  if(!entries.length)return;
  if(d.last_at&&time<Date.parse(d.last_at))d.clock_warning=true;
  d.local_state=model;d.queue.push(...entries);d.next+=entries.length;d.last_at=!d.last_at||time>=Date.parse(d.last_at)?at:d.last_at;
  try{await this.save();}catch(error){this.disk=undefined;throw error;}
 }
 async execute(command:string,data:Record<string,any>,id:string,at:string){return this.exclusive(async()=>{const d=await this.load();await this.applyCommands(d,[{command,data}],id,at);return JSON.parse(JSON.stringify(d.local_state));});}
 private currentAdvice(d:Disk){return this.adviceRevision===d.local_state.revision&&this.adviceScope===d.package.sha256+'|'+d.local_state.round_id&&this.advice?.policy_version===coreFor(d.local_state.core_version).strategy_policy_version;}
 private plan(d:Disk,intent:PlanIntent={}){
  const key=JSON.stringify(intent);
  if(!this.currentAdvice(d)||this.adviceIntent!==key){this.advice=coreForPackage(d.package.package).planStrategy(d.package.package,d.local_state,intent as any);this.adviceRevision=d.local_state.revision;this.adviceIntent=key;this.adviceScope=d.package.sha256+'|'+d.local_state.round_id;}
  return this.advice;
 }
 async strategy(intent:PlanIntent={}){return this.exclusive(async()=>{const d=await this.load();if(d.lease?.status!=='active'||!d.local_state)throw Error('请先准备本机球局。');return JSON.parse(JSON.stringify(this.plan(d,intent)));});}
 async turn(text:string,id:string,at:string){return this.exclusive(async()=>{
  const d=await this.load();const engine=coreForPackage(d.package?.package);if(!d.local_state)throw Error('本地规则球局尚未准备。');
  const query=/怎么打|如何打|什么风险|下杆.*风险|下一杆.*风险|其他.*(?:方案|路线|策略)|其它.*(?:方案|路线|策略)|进取方案|保守|稳一点|稳妥|安全.*(?:方案|策略)|分两杆|过渡|想打短一点/.test(text);
  if(query&&!engine.parsePreference(text)&&!d.local_state.pending&&!d.local_state.draft&&d.local_state.stage==='playing'){
   const kind=/进取方案/.test(text)?'aggressive':/保守|安全|稳一点|稳妥/.test(text)?'conservative':/过渡|分两杆|打短一点/.test(text)?'layup':/其他|其它/.test(text)?'alternative':'default';
   const exclude=kind==='alternative'&&this.currentAdvice(d)?this.advice?.options?.[0]?.club:undefined;
   const plan=this.plan(d,{kind,...(exclude?{exclude_club:exclude,exclude_aim:this.advice?.options?.[0]?.aim_point}:{})});
   return {text:plan.text,local_state:JSON.parse(JSON.stringify(d.local_state)),choices:plan.question==='finder_club'?['5号木','铁木杆','4号铁','其他方案']:plan.question==='finder_carry'?['其他方案']:plan.question==='pin'?['左前','中部','右后','跳过旗位']:plan.question==='lie'?['球道','长草','沙坑','果岭上']:plan.question==='fairway_carry'?['跳过球道杆距','没有球道木和铁木杆']:plan.question==='ball_outcome'?['确认在界内','确认出界','确认下水']:engine.localChoices(d.local_state),totals:engine.localTotals(d.local_state),strategy:plan,clock_warning:Boolean(d.clock_warning)};
  }
  const previousIntent=this.currentAdvice(d)?JSON.parse(this.adviceIntent):undefined;
  const previousQuestion=this.currentAdvice(d)?this.advice?.question:null;
  const normalized=previousQuestion==='finder_carry'&&/^\d{1,3}(?:码|米)?$/.test(text)?this.advice.missing_club+text:previousQuestion==='fairway_carry'&&/^(跳过|不知道)$/.test(text)?'跳过球道杆距':previousQuestion==='fairway_carry'&&text==='没有'?'没有球道木和铁木杆':previousQuestion==='pin'&&/^(跳过|不知道)$/.test(text)?'跳过旗位':text;
  let turn=engine.parseLocalTurn(d.local_state,normalized);if('adaptFinderReply' in engine)turn=engine.adaptFinderReply(d.local_state,turn,previousQuestion);
  if(previousQuestion==='ball_outcome'&&/^(确认在界内|确认出界|确认OB|确认下水)$/i.test(normalized)){const cause=this.advice.suspected;turn=engine.parseLocalTurn({...d.local_state,pending:{phase:'uncertain',cause}},normalized);turn.commands.unshift({command:'report_incident',data:{cause}});}
  if(this.currentAdvice(d))for(const cmd of turn.commands)if(cmd.command==='select_club'){const target=this.advice?.options?.find((option:any)=>option.club===cmd.data.club);if(target){cmd.data.target=target.aim_point;const kind=JSON.parse(this.adviceIntent??'{}').kind;if(engine.personal_strategy&&(kind==='conservative'||kind==='layup'))cmd.data.strategy_choice='control';else if(engine.personal_strategy&&kind==='aggressive')cmd.data.strategy_choice='distance';}}
  if(turn.commands.length)await this.applyCommands(d,turn.commands,id,at);
  let response=turn.text,plan;
  if(turn.commands.length&&(previousQuestion||['conservative','alternative'].includes(previousIntent?.kind)&&turn.commands.some(c=>['set_club_carry','set_fairway_finder'].includes(c.command)))&&turn.commands.every(c=>['set_pin','set_lie','set_club_purpose','set_club_carry','set_fairway_finder','set_fairway_carry_status','set_position'].includes(c.command))){plan=this.plan(d,previousIntent??{});response=turn.text+plan.text;}
  return {text:response,local_state:JSON.parse(JSON.stringify(d.local_state)),choices:plan?.question==='finder_club'?['5号木','铁木杆','4号铁','其他方案']:plan?.question==='finder_carry'?['其他方案']:engine.localChoices(d.local_state),totals:engine.localTotals(d.local_state),strategy:plan,clock_warning:Boolean(d.clock_warning)};
 });}

 private snapshotDisk(d:Disk):Disk{const {package:pack,local_state:model,...mutable}=d;return {...JSON.parse(JSON.stringify(mutable)),package:pack,local_state:model?{round_id:model.round_id,receipts:JSON.parse(JSON.stringify(model.receipts))}:undefined};}
 private validateLease(lease:any,expected:Lease,min:number,max:number,states=['active']){
  if(!lease||['lease_id','round_id','device_id','sha256','base_version'].some(key=>lease[key]!==expected[key as keyof Lease])||!Number.isInteger(lease.cursor)||lease.cursor<min||lease.cursor>max||!states.includes(lease.status))throw Error('同步回执身份或进度不一致，本机队列未确认。');
 }
 private summary(model:any){return {revision:model.revision,hole:model.hole,stage:model.stage,totals:coreFor(model.core_version).localTotals(model),pending:model.pending?.phase??null,draft:Boolean(model.draft)};}
 private async expectedPrefix(snapshot:Disk,cursor:number,epoch:number){
  if(!snapshot.local_state)throw Error('本机缺少共用核心状态，不能核对同步进度。');
  let model=this.ackModel&&this.ackModel.round_id===snapshot.local_state.round_id&&this.ackModel.revision<=cursor?this.ackModel:coreForPackage(snapshot.package.package).createLocalRound(snapshot.package.package);
  const events=Object.values(snapshot.local_state.receipts).filter((e:any)=>e.expected_revision>=model.revision&&e.expected_revision<cursor).sort((a:any,b:any)=>a.expected_revision-b.expected_revision);
  for(const [index,event] of events.entries()){this.checkGeneration(epoch);model=coreFor(model.core_version).applyLocalCommand(model,event as any);if(index%4===3)await new Promise(resolve=>setTimeout(resolve,0));}
  if(model.revision!==cursor)throw Error('本机缺少对应同步进度的事件，队列未确认。');return model;
 }
 private async acceptReply(reply:any,snapshot:Disk,max:number,epoch:number,batch?:Entry[]){
  this.checkGeneration(epoch);this.validateLease(reply?.offline,snapshot.lease!,snapshot.lease!.cursor,max,['active','released']);
  if(batch){if(reply.offline.status!=='active'||reply.offline.cursor!==max||!Array.isArray(reply.accepted)||reply.accepted.length!==batch.length||batch.some((entry,i)=>reply.accepted[i].seq!==entry.seq||reply.accepted[i].event_id!==entry.event.event_id||reply.accepted[i].version!==snapshot.lease!.base_version+entry.seq))throw Error('同步事件回执不完整，本机队列未确认。');}
  const prefix=await this.expectedPrefix(snapshot,reply.offline.cursor,epoch);
  if(prefix&&(!reply.local_status||canonical(this.summary(prefix))!==canonical(reply.local_status)))throw Error('服务器缺少有效的球局核对结果，本机队列未确认。');
  await this.exclusive(async()=>{
   this.checkGeneration(epoch);const d=await this.load();this.validateLease(reply.offline,d.lease!,d.lease!.cursor,d.next-1,['active','released']);
   const previous=d.lease,queue=d.queue,conflict=d.conflict;delete d.conflict;d.lease=reply.offline;d.queue=d.queue.filter(entry=>entry.seq>reply.offline.cursor);
   try{await this.save();this.ackModel=prefix;}catch(error){d.lease=previous;d.queue=queue;d.conflict=conflict;this.disk=undefined;throw error;}
  });
 }
 async synchronize(){
  if(this.syncing)throw Error('本次同步尚未结束，本地记分可继续。');this.syncing=true;const epoch=this.generation;
  try{
   const snapshot=await this.exclusive(async()=>{const d=await this.load();if(!d.lease||d.lease.status==='preparing')throw Error('请先完成离线准备。');return this.snapshotDisk(d);});
   if(snapshot.native_start&&!snapshot.native_start.registered){
    const registration=await request(this.base,'/offline-rounds',this.token,{action:'register',...snapshot.native_start.registration});
    const lease=registration.offline;
    this.validateLease(lease,{...snapshot.lease!,lease_id:lease?.lease_id},0,0,['active']);
    if(typeof lease.lease_id!=='string'||!lease.lease_id)throw Error('离线注册回执无效。');
    await this.exclusive(async()=>{this.checkGeneration(epoch);const d=await this.load();if(d.local_state?.round_id!==snapshot.local_state!.round_id)throw Error('本机球局已切换。');d.lease=lease;d.native_start!.registered=true;await this.save();});
    snapshot.lease=lease;snapshot.native_start.registered=true;
   }
   const route=snapshot.native_start?'/offline-rounds':'/journey';const roundScope=snapshot.native_start?{round_id:snapshot.lease!.round_id}:{};
   const status=await request(this.base,route,this.token,{...roundScope,action:snapshot.native_start?'status':'offline_status',device_id:snapshot.device_id,lease_id:snapshot.lease!.lease_id});
   await this.acceptReply(status,snapshot,snapshot.next-1,epoch);let result=status;
   while(true){
    this.checkGeneration(epoch);const current=await this.exclusive(async()=>this.snapshotDisk(await this.load()));if(!current.queue.length)return result;
    const batch=current.queue.slice(0,100);
    const reply=await request(this.base,route,this.token,{...roundScope,action:snapshot.native_start?'sync':'offline_sync',device_id:current.device_id,lease_id:current.lease!.lease_id,sha256:current.lease!.sha256,events:batch});
    await this.acceptReply(reply,current,batch[batch.length-1].seq,epoch,batch);result=reply;
   }
  }finally{this.syncing=false;}
 }
 async recoverReleasedRound(){return this.exclusive(async()=>{
  const d=await this.load();if(!d.native_start||d.lease?.status!=='released'||d.local_state?.finished||d.queue.length)throw Error('当前球局无需恢复记录权。');
  const reply=await request(this.base,'/offline-rounds',this.token,{action:'resume_recording',round_id:d.lease.round_id,device_id:d.device_id,lease_id:d.lease.lease_id,cursor:d.lease.cursor});
  this.validateLease(reply.offline,d.lease,d.lease.cursor,d.lease.cursor,['active']);d.lease=reply.offline;await this.save();return this.cached();
 });}
 async release(){return this.exclusive(async()=>{
  if(this.syncing)throw Error('请等待本次同步结束。');const d=await this.load();if(d.conflict)throw Error(d.conflict);if(!d.lease)throw Error('尚未准备离线球局。');if(d.queue.length)throw Error('请先同步全部离线记录。');if(d.native_start&&!d.local_state?.finished)throw Error('请先确认结束本场球局；进行中请使用普通同步。');
  const reply=await request(this.base,d.native_start?'/offline-rounds':'/journey',this.token,{...(d.native_start?{round_id:d.lease.round_id}:{}),action:d.native_start?'release':'offline_release',device_id:d.device_id,lease_id:d.lease.lease_id,cursor:d.lease.cursor});this.validateLease(reply.offline,d.lease,d.lease.cursor,d.lease.cursor,['released']);d.lease=reply.offline;await this.save();return reply;
 });}
}
