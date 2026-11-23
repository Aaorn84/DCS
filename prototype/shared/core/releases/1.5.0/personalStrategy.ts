/** Course-independent user facts. Outcome evidence describes capability, never inferred intent. */
import {fairwayFinder,normalizeClub,type Club} from './bag.ts';
export type StrategyPreference='balanced'|'distance'|'control';
export type PersonalStrategy={version:1;preference:StrategyPreference;source:'system_default'|'user_report'|'observed_choices';choice_samples:number;choice_rounds:number;finder:string|null;trusted_clubs:string[];evidence:Record<string,{samples:number;source:'observed_final_rest_pattern';confidence:'developing'|'established'}>};
export function parseStrategyPreference(text:string):StrategyPreference|null{
 const clean=text.replace(/[\s，,。！？!?]/g,'');
 if(/^(?:以后|平时|默认)(?:我)?(?:更)?(?:偏向|喜欢|优先|采用)(?:保守|稳妥|稳健)(?:打法|策略)?$/.test(clean))return 'control';
 if(/^(?:以后|平时|默认)(?:我)?(?:更)?(?:偏向|喜欢|优先|采用)(?:距离|进取|进攻)(?:打法|策略)?$/.test(clean))return 'distance';
 if(/^(?:恢复|改为|默认采用)(?:系统默认|均衡)(?:打法|策略)?$/.test(clean))return 'balanced';
 return null;
}
export function personalStrategy(profile:any,dispersion:any={}):PersonalStrategy{
 const declared=profile.strategy_preference;
 const explicit=declared?.source==='user_report'&&['balanced','distance','control'].includes(declared.value);
 const usage=(Array.isArray(profile.strategy_usage)?profile.strategy_usage:[]).slice(-60).filter((r:any)=>typeof r.round_id==='string'&&['control','distance'].includes(r.mode));
 const rounds=new Set(usage.map((r:any)=>r.round_id)).size,control=usage.filter((r:any)=>r.mode==='control').length;
 const learned=usage.length>=8&&rounds>=3?(control/usage.length>=.7?'control':control/usage.length<=.3?'distance':null):null;
 const evidence:PersonalStrategy['evidence']={};
 // Aggregates are already computed outside the speech path. Bound work; don't load shot history here.
 for(const [label,row] of Object.entries(dispersion??{}).slice(0,32) as [string,any][]){
  if(!Number.isInteger(row?.samples)||row.samples<10||!Number.isFinite(row.lateral_p10_m)||!Number.isFinite(row.lateral_p90_m)||row.lateral_p10_m>row.lateral_p90_m)continue;
  const club=normalizeClub(label);evidence[club]={samples:row.samples,source:'observed_final_rest_pattern',confidence:row.samples>=30?'established':'developing'};
 }
 const trusted=Object.entries(dispersion??{}).slice(0,32).filter(([label,row]:[string,any])=>{
  const e=evidence[normalizeClub(label)];return e?.confidence==='established'&&Math.max(Math.abs(row.lateral_p10_m),Math.abs(row.lateral_p90_m))<=15;
 }).map(([label])=>normalizeClub(label));
 return {version:1,preference:explicit?declared.value:learned??'balanced',source:explicit?'user_report':learned?'observed_choices':'system_default',choice_samples:usage.length,choice_rounds:rounds,finder:fairwayFinder(profile)??null,trusted_clubs:trusted,evidence};
}

/** Only an explicit route request followed by an actual stroke counts as a preference observation. */
export function appendStrategyUsage(profile:any,round_id:string,hole:number,mode:string|undefined){
 if(!['control','distance'].includes(mode??''))return;
 const rows=(Array.isArray(profile.strategy_usage)?profile.strategy_usage:[]).filter((r:any)=>!(r.round_id===round_id&&r.hole===hole));
 profile.strategy_usage=[...rows,{round_id,hole,mode}].slice(-60);
}

export function planningPattern(dispersion:any,profile:any,club:Club,carry:number){
 const known=dispersion?.[club.label];const reliable=known&&known.samples>=10&&[known.lateral_p10_m,known.lateral_p90_m,known.lateral_median_m].every(Number.isFinite);
 // Planning envelope, NOT a success probability; shorter clubs do not get a safety label.
 const lateral=reliable?Math.max(6,Math.abs(known.lateral_p10_m),Math.abs(known.lateral_p90_m)):Math.max(6,carry*.9144*.11);
 const miss=profile.usual_miss?.value;const bias=reliable?known.lateral_median_m:miss==='偏右'?lateral*.25:miss==='偏左'?-lateral*.25:0;
 return {lateral,bias,longitudinal:Math.max(4,carry*.9144*.07),source:reliable?'observed_final_rest_pattern':'provisional_planning_envelope'};
}
