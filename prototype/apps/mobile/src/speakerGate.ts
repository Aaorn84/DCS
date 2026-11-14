/** This is an interaction filter, not account authentication. */
export const enrollmentCount=3;
export const minimumClipMs=1200;
export const minimumEnrollmentMs=2500;
export const matchThreshold=.70; // Initial development setting; tune on real field recordings.
export type SpeakerProfile={enabled:boolean;template?:string};
function normalize(values:number[]) {
  if(values.length<16||values.length>512||values.some(v=>!Number.isFinite(v)))return null;
  const norm=Math.hypot(...values);
  return norm>0&&Number.isFinite(norm)?values.map(v=>v/norm):null;
}
function dot(a:number[],b:number[]) {
  return a.length===b.length?a.reduce((sum,v,i)=>sum+v*b[i],0):-1;
}
export function enroll(samples:number[][]):string|null {
  if(samples.length!==enrollmentCount)return null;
  const units=samples.map(normalize);
  if(units.some(a=>!a))return null;
  const valid=units as number[][];
  if(valid.some((a,i)=>valid.slice(0,i).some(b=>dot(a,b)<matchThreshold)))return null;
  const center=normalize(valid[0].map((_,i)=>valid.reduce((s,a)=>s+a[i],0)));
  return center?.map(v=>(Math.round(v*32767)+32768).toString(16).padStart(4,'0')).join('')??null;
}
export function matches(template:string|undefined,embedding:number[]) {
  if(!template||! /^(?:[0-9a-f]{4}){16,512}$/.test(template))return false;
  const enrolled=normalize((template.match(/.{4}/g)??[]).map(v=>parseInt(v,16)-32768));
  const current=normalize(embedding);
  return !!enrolled&&!!current&&dot(enrolled,current)>=matchThreshold;
}
export async function verifyThenTranscribe(input:{
  profile:SpeakerProfile;durationMs:number;isCurrent:()=>boolean;
  embedding:()=>Promise<number[]>;transcribe:()=>Promise<string>;
}):Promise<string|null>{
  const {profile,durationMs,isCurrent}=input;
  if(!profile.enabled||!profile.template||!Number.isFinite(durationMs)||durationMs<minimumClipMs||!isCurrent())return null;
  let embedding:number[];
  try{embedding=await input.embedding();}catch{return null;}
  if(!isCurrent()||!matches(profile.template,embedding))return null;
  const text=await input.transcribe();
  return isCurrent()?text.trim()||null:null;
}
