import {CORE_VERSION,CORE_DATASET} from './protocol.ts';
import {normalizeClub} from './bag.ts';
import {createLocalRound,CoreRuleError} from './roundEngine.ts';
export function canonicalJson(v:any):string{if(Array.isArray(v))return '['+v.map(canonicalJson).join(',')+']';if(v&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonicalJson(v[k])).join(',')+'}';return JSON.stringify(v);}
const clone=(v:any)=>JSON.parse(JSON.stringify(v));
const require=(ok:any,message:string)=>{if(!ok)throw new CoreRuleError(message);};
export type SetupPatch={name?:string;proactive?:boolean;shot_recording?:boolean;usual_miss?:string;units?:'码'|'米';carries?:Record<string,{low:number;high:number;role?:string}>;finder?:string|null};
export function setupProfile(base:any,patch:SetupPatch={}){
 require(patch&&typeof patch==='object'&&!Array.isArray(patch),'invalid local profile');
 require(Object.keys(patch).every(k=>['name','proactive','shot_recording','usual_miss','units','carries','finder'].includes(k)),'unsupported local profile field');
 const profile=clone(base??{});
 for(const key of ['name','usual_miss'] as const)if(patch[key]!==undefined){require(typeof patch[key]==='string'&&patch[key]!.length<=100,'invalid profile text');profile[key]={value:patch[key],source:'user_report'};}
 for(const key of ['proactive','shot_recording'] as const)if(patch[key]!==undefined){require(typeof patch[key]==='boolean','invalid profile preference');profile[key]={value:patch[key],source:'user_report'};}
 if(patch.units!==undefined){require(['码','米'].includes(patch.units),'invalid distance units');profile.units={value:patch.units,source:'user_report'};}
 if(patch.carries!==undefined){
  require(patch.carries&&typeof patch.carries==='object'&&!Array.isArray(patch.carries)&&Object.keys(patch.carries).length<=30,'invalid carry list');
  for(const [label,value] of Object.entries(patch.carries)){
   const club=normalizeClub(label);require(/^(一号木|[3-9]号木|(?:[2-9]号)?铁木杆|[2-9]号铁|P杆|[4-6]\d度杆)$/.test(club),'unsupported carry club');
   require(value&&Number.isFinite(value.low)&&Number.isFinite(value.high)&&value.low>=0&&value.high>0&&value.low<=value.high&&value.high<=400,'invalid carry range');
   require(value.role===undefined||value.role==='沙坑','invalid club purpose');
   const keys:Record<string,string>={'一号木':'driver','3号木':'three_wood','5号木':'five_wood','铁木杆':'hybrid','7号铁':'seven','3号铁':'iron3','4号铁':'iron4','P杆':'pitching_wedge'};
   if(keys[club]&&value.low===value.high)profile[keys[club]]={value:{distance:value.high,units:'码',distance_type:'carry',club_name:club},source:'user_report'};
   profile.bag_overrides={...(profile.bag_overrides??{}),[club]:{low:value.low,high:value.high,source:'user_report',...(value.role?{role:value.role}:{})}};
  }
 }
 if(patch.finder!==undefined){if(patch.finder===null)delete profile.fairway_finder;else{const club=normalizeClub(patch.finder);require(/^(一号木|[3-9]号木|(?:[2-9]号)?铁木杆|[2-9]号铁)$/.test(club),'invalid fairway finder');profile.fairway_finder={value:{club},source:'user_report'};}}
 return profile;
}
export function validateCourseAsset(asset:any){
 require(asset?.schema===1&&asset.core_version===CORE_VERSION&&asset.dataset===CORE_DATASET,'course core version mismatch');
 require(asset.course?.course_id&&asset.course?.map_version&&asset.course?.crs==='WGS84','invalid downloaded course');
 require(Array.isArray(asset.tees)&&asset.tees.length>0&&asset.tees.every((v:any)=>typeof v==='string'&&v.length>0&&v.length<=30),'downloaded Tee unavailable');
 require(Array.isArray(asset.course.holes)&&asset.course.holes.length===18,'18 holes required');
 const seen=new Set();for(const h of asset.course.holes){require(Number.isInteger(h.number)&&h.number>=1&&h.number<=18&&!seen.has(h.number)&&Number.isInteger(h.par)&&h.par>=2&&h.par<=7,'invalid course hole');seen.add(h.number);}
 return asset;
}
/** Both phone and backend build the exact same immutable round seed from known downloads. */
export function assembleOfflinePackage(asset:any,context:any,setup:any,round:any){
 validateCourseAsset(asset);
 require(Array.isArray(asset.tees)&&asset.tees.includes(round?.tee),'downloaded Tee unavailable');
 require(round&&/^[A-Za-z0-9_-]{8,90}$/.test(round.id)&&round.course===asset.course.course_id,'invalid local round identity');
 require(Number.isInteger(round.start_hole)&&round.start_hole>=1&&round.start_hole<=18,'invalid starting hole');
 require(typeof round.started_at==='string'&&/(Z|[+-]\d\d:\d\d)$/.test(round.started_at)&&Number.isFinite(Date.parse(round.started_at)),'invalid local start time');
 require(setup&&typeof setup.memory_allowed==='boolean'&&Object.keys(setup).every(k=>['memory_allowed','patch'].includes(k)),'invalid memory preference');
 const profile=setupProfile(setup.memory_allowed?context?.profile:{},setup.patch);
 const pack={schema:1,core_version:CORE_VERSION,dataset:CORE_DATASET,local_rules_version:1,local_command_semantics:2,
  round:{id:round.id,course:round.course,tee:round.tee,start_hole:round.start_hole,started_at:round.started_at,finished:false},course:clone(asset.course),profile,
  dispersion:clone(setup.memory_allowed?context?.dispersion??{}:{}),history_by_hole:clone(setup.memory_allowed?context?.history_by_hole??{}:{}),
  capabilities:{local_round_engine:true,local_strategy_engine:true,full_round_offline:false}};
 createLocalRound(pack);return pack;
}
