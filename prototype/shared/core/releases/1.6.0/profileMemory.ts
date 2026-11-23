/** Small, versioned user facts; no map, shot ledger or strategy computation. */
import {bag} from './bag.ts';
import type {SetupPatch} from './offlineSetup.ts';
export type FieldClock={at:string;round_id:string;order:number};
const scalar=['personal_note','name','proactive','shot_recording','usual_miss','units','driver','three_wood','five_wood','hybrid','seven','iron3','iron4','pitching_wedge','long_iron','fairway_finder','strategy_preference','fairway_carry_status','strategy_usage'];
const nested:Record<string,string>={'bag:':'bag_overrides','purpose:':'lofted_wedge_uses','range:':'lofted_wedge_ranges'};
export function profileFacts(profile:any){
 const fields:Record<string,any>={};for(const key of scalar)if(profile?.[key]!==undefined)fields[key]=profile[key];
 for(const [prefix,key] of Object.entries(nested))for(const [label,value] of Object.entries((key==='bag_overrides'?profile?.[key]:profile?.[key]?.value)??{}))fields[prefix+label]=value;
 return fields;
}
export function profileFromFacts(fields:Record<string,any>,clocks:Record<string,FieldClock>={}){
 const profile:any={};for(const [field,value] of Object.entries(fields)){
  if(scalar.includes(field))profile[field]=value;
  else for(const [prefix,key] of Object.entries(nested))if(field.startsWith(prefix)){
   if(key==='bag_overrides')(profile[key]??={})[field.slice(prefix.length)]=value;
   else (profile[key]??={value:{},source:'user_report'}).value[field.slice(prefix.length)]=value;
  }
 }if(Object.keys(clocks).length)profile.field_versions=clocks;return profile;
}
const serial=(v:any)=>JSON.stringify(v);
export function stampProfileChanges(before:any,after:any,clock:FieldClock){
 const a=profileFacts(before),b=profileFacts(after);const versions={...(after.field_versions??{})};
 for(const [key,value] of Object.entries(b))if(serial(a[key])!==serial(value))versions[key]={...clock};
 if(Object.keys(versions).length)after.field_versions=versions;
}
export function mergeProfileMemory(base:any,incoming:any){
 const fields={...profileFacts(base)},clocks={...(base?.field_versions??{})};
 for(const [key,value] of Object.entries(profileFacts(incoming))){
  const a=clocks[key],b=incoming?.field_versions?.[key];
  if(a&&b&&(Date.parse(a.at)>Date.parse(b.at)||Date.parse(a.at)===Date.parse(b.at)&&a.order>b.order))continue;
  fields[key]=value;if(b)clocks[key]=b;
 }
 return {...base,...incoming,...profileFromFacts(fields,clocks)};
}
export function patchFromProfile(profile:any):SetupPatch{
 const patch:SetupPatch={carries:{},field_versions:profile.field_versions??{}};
 for(const c of bag(profile))if(!c.estimated&&!c.purposeOnly)patch.carries![c.label]={low:c.low,high:c.high,...(c.role?{role:c.role}:{})};
 for(const key of ['name','proactive','shot_recording','usual_miss','units'] as const)if(profile[key]?.source==='user_report')(patch as any)[key]=profile[key].value;
 if(profile.fairway_finder===null)patch.finder=null;const finder=profile.fairway_finder?.value;if(finder)patch.finder=typeof finder==='string'?finder:finder.club;
 if(profile.strategy_preference?.source==='user_report')patch.strategy_preference=profile.strategy_preference.value;
 if(profile.strategy_usage)patch.strategy_usage=profile.strategy_usage;
 if(profile.lofted_wedge_uses?.value)patch.purposes=profile.lofted_wedge_uses.value;
 if(profile.fairway_carry_status)patch.fairway_status=profile.fairway_carry_status;
 return patch;
}
