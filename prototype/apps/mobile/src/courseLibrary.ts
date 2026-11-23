import {patchFromProfile,stampProfileChanges} from '../../../shared/core/profileMemory.ts';
import {coreForPackage,coreFor} from '../../../shared/core/runtime.ts';
import type {LocalStore} from './journeyPersistence.ts';
import {savePackage,loadPackage,removePackage} from './immutablePackage.ts';
import {decodeLocalState} from './localStateCodec.ts';
import {request} from './api.ts';
import {CORE_VERSION,CORE_DATASET} from '../../../shared/core/protocol.ts';
import {canonicalJson,assembleOfflinePackage,validateCourseAsset,setupProfile,type SetupPatch} from '../../../shared/core/offlineSetup.ts';
export type SetupDraft={memory_allowed:boolean;patch:SetupPatch;stage:string;course_id?:string;tee?:string;start_hole:number};
type Download={course_id:string;name:string;tee:string;asset_sha256:string;context_sha256:string;downloaded_at:string};
type LocalRecord={id:string;key:string;phase:'preparing'|'active';spec:any};
type LibraryDisk={schema:1;catalog:any[];downloads:Download[];draft:SetupDraft;rounds:LocalRecord[];active_id?:string};
const blank=():SetupDraft=>({memory_allowed:false,patch:{},stage:'memory',start_hole:1});
/** Account-scoped metadata commits are small; maps are stored once per immutable digest. */
export class CourseLibrary{
 private tail:Promise<void>=Promise.resolve();
 private maps=new Map<string,any>();
 constructor(private base:string,private token:string,private store:LocalStore,private key:string,private newId:()=>string,private sha:(s:string)=>Promise<string>){}
 private async serial<T>(fn:()=>Promise<T>){const before=this.tail;let done!:()=>void;this.tail=new Promise(resolve=>done=resolve);await before;try{return await fn();}finally{done();}}
 async read():Promise<LibraryDisk>{const raw=await this.store.getItem(this.key);if(!raw)return {schema:1,catalog:[],downloads:[],draft:blank(),rounds:[]};const d=JSON.parse(raw);if(d.schema!==1||!Array.isArray(d.downloads)||!Array.isArray(d.rounds)||d.rounds.some((r:any)=>!r||typeof r.id!=='string'||r.key!==this.key+'.round.'+r.id))throw Error('本机球场目录损坏，请保留数据。');return d;}
 private async save(d:LibraryDisk){await this.store.setItem(this.key,JSON.stringify(d));}
 async saveDraft(draft:SetupDraft){setupProfile({},draft.patch);if(typeof draft.memory_allowed!=='boolean'||!Number.isInteger(draft.start_hole)||draft.start_hole<1||draft.start_hole>18)throw Error('本机资料无效。');return this.serial(async()=>{const d=await this.read();const before=setupProfile({},d.draft.patch),after=setupProfile({},draft.patch);stampProfileChanges(before,after,{at:new Date().toISOString(),round_id:'local-profile',order:Math.max(0,...Object.values(after.field_versions??{}).map((v:any)=>v.order))+1});d.draft=JSON.parse(JSON.stringify(draft));if(after.field_versions)d.draft.patch.field_versions=after.field_versions;await this.save(d);return d;});}
 async catalog(){const reply=await request(this.base,'/courses',this.token);if(!Array.isArray(reply.courses))throw Error('球场目录无效。');return this.serial(async()=>{const d=await this.read();d.catalog=reply.courses;await this.save(d);return d;});}
 async download(course_id:string,tee:string){
  const draft=(await this.read()).draft;const reply=await request(this.base,'/courses',this.token,{course_id,tee,include_personal:draft.memory_allowed});const pack=reply.asset;
  if(!pack||typeof pack.payload_json!=='string'||await this.sha(pack.payload_json)!==pack.sha256||canonicalJson(JSON.parse(pack.payload_json))!==canonicalJson(pack.package))throw Error('球场下载校验失败，原地图保留。');
  if(pack.package.core_version!==CORE_VERSION||pack.package.dataset!==CORE_DATASET||pack.package.course?.course_id!==course_id||!pack.package.tees?.includes(tee))throw Error('地图或Tee版本不匹配。');
  validateCourseAsset(pack.package);
  const context=reply.context;if(typeof context?.payload_json!=='string'||await this.sha(context.payload_json)!==context.sha256)throw Error('个人参考资料校验失败。');
  const personal=JSON.parse(context.payload_json);if(personal.asset_sha256!==pack.sha256)throw Error('个人参考资料与地图不一致。');
  // Complete and verify immutable bytes before replacing the visible directory pointer.
  await savePackage(this.store,this.key+'.package.course.'+pack.sha256,pack);
  await this.loadMap(pack.sha256,true);
  await savePackage(this.store,this.key+'.package.context.'+context.sha256,{payload_json:context.payload_json,sha256:context.sha256});
  return this.serial(async()=>{const d=await this.read();const name=d.catalog.find(c=>c.course_id===course_id)?.name??course_id;
   d.downloads=d.downloads.filter(c=>c.course_id!==course_id||c.tee!==tee);d.downloads.push({course_id,name,tee,asset_sha256:pack.sha256,context_sha256:context.sha256,downloaded_at:new Date().toISOString()});await this.save(d);return d;});
 }
 private async loadMap(digest:string,verify=false){
  if(!/^[a-f0-9]{64}$/.test(digest))throw Error('地图摘要无效。');
  if(!verify&&this.maps.has(digest))return this.maps.get(digest);
  const pack=await loadPackage(this.store,this.key+'.package.course.'+digest);
  if(await this.sha(pack.payload_json)!==digest||pack.sha256!==digest||!coreForPackage({...pack.package,local_rules_version:1,local_command_semantics:2}))throw Error('本机地图校验失败，请保留已有球局。');
  this.maps.delete(digest);this.maps.set(digest,pack.package);while(this.maps.size>3)this.maps.delete(this.maps.keys().next().value!);return pack.package;
 }
 async remove(course_id:string,tee:string){return this.serial(async()=>{const d=await this.read();const removed=d.downloads.find(c=>c.course_id===course_id&&c.tee===tee);if(removed&&d.rounds.some(r=>r.phase==='preparing'&&r.spec.asset_sha256===removed.asset_sha256))throw Error('请先完成该球场的本机开局恢复。');d.downloads=d.downloads.filter(c=>c!==removed);await this.save(d);if(removed&&!d.downloads.some(c=>c.asset_sha256===removed.asset_sha256)){this.maps.delete(removed.asset_sha256);await removePackage(this.store,this.key+'.package.course.'+removed.asset_sha256).catch(()=>{});}return d;});}
 async prepareLocalRound(){return this.serial(async()=>{
  const d=await this.read(),draft=d.draft;const active=d.rounds.find(r=>r.id===d.active_id);if(active?.phase==='preparing')return active;if(active){const stored=await this.store.getItem(active.key);if(!stored||!decodeLocalState(JSON.parse(stored).local_state)?.finished)throw Error('请先完成当前本机球局，不能覆盖记录。');}const selected=d.downloads.find(c=>c.course_id===draft.course_id&&c.tee===draft.tee);if(!selected)throw Error('请先下载所选球场和Tee，再离线开局。');
  const asset=await this.loadMap(selected.asset_sha256,true);if(asset.core_version!==CORE_VERSION)throw Error('新球局请更新球场资料；已有球局可继续恢复。');const id=this.newId(),round={id,course:draft.course_id,tee:draft.tee,start_hole:draft.start_hole,started_at:new Date().toISOString()};
  const context=await this.loadContext(selected.context_sha256);const setup={memory_allowed:draft.memory_allowed,patch:draft.patch};const pack=assembleOfflinePackage(asset,context,setup,round);const raw=canonicalJson(pack),digest=await this.sha(raw);
  const spec={round,setup,asset_sha256:selected.asset_sha256,context_sha256:selected.context_sha256,package_sha256:digest};
  const record:LocalRecord={id,key:this.key+'.round.'+id,phase:'preparing',spec};d.rounds.push(record);d.active_id=id;await this.save(d);return record;
 });}
 private async loadContext(digest:string){const context=await loadPackage(this.store,this.key+'.package.context.'+digest);if(await this.sha(context.payload_json)!==digest)throw Error('本机个人参考资料校验失败。');return context.package;}
 async materialize(record:LocalRecord){const asset=await this.loadMap(record.spec.asset_sha256,true),context=await this.loadContext(record.spec.context_sha256);const pack=coreFor(asset.core_version).assembleOfflinePackage(asset,context,record.spec.setup,record.spec.round);const raw=canonicalJson(pack);if(await this.sha(raw)!==record.spec.package_sha256)throw Error('本机开局资料与原始选择不一致。');return {...record.spec,package:{package:pack,payload_json:raw,sha256:record.spec.package_sha256,source_version:0}};}
 async activate(id:string){return this.serial(async()=>{const d=await this.read();const row=d.rounds.find(r=>r.id===id);if(!row)throw Error('本机球局索引缺失。');row.phase='active';d.active_id=id;await this.save(d);return row;});}
 async select(id:string){return this.serial(async()=>{const d=await this.read();const row=d.rounds.find(r=>r.id===id);if(!row)throw Error('本机球局不存在。');d.active_id=id;await this.save(d);return row;});}
 async profilePreview(){const d=await this.read();const selected=d.downloads.find(c=>c.course_id===d.draft.course_id&&c.tee===d.draft.tee)??d.downloads.at(-1);const context=selected&&d.draft.memory_allowed?await this.loadContext(selected.context_sha256):{};return setupProfile(context.profile,d.draft.patch);}
 async nextSetup(){return this.serial(async()=>{const d=await this.read();const active=d.rounds.find(r=>r.id===d.active_id);if(active){const raw=await this.store.getItem(active.key);const finished=raw&&decodeLocalState(JSON.parse(raw).local_state);if(!finished?.finished)throw Error('当前球局尚未结束，记录已保留。');if(d.draft.memory_allowed){d.draft.patch={...d.draft.patch,...patchFromProfile(finished.profile)};}}if(!d.draft.memory_allowed)d.draft={...blank(),stage:'course'};else d.draft.stage='course';delete d.active_id;await this.save(d);return d;});}
 async active(){const d=await this.read();return d.rounds.find(r=>r.id===d.active_id);}
}
