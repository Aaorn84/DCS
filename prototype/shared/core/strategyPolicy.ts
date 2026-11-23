/** System-wide strategy policy. No map access, rules mutation or per-course exceptions. */
import type {Candidate} from './courseAnalysis.ts';
import type {PersonalStrategy,StrategyPreference} from './personalStrategy.ts';
export const STRATEGY_POLICY_VERSION=4;
export type StrategyPolicy={version:4;mode:StrategyPreference;explicit_turn:boolean};
export function resolveStrategyPolicy(personal:PersonalStrategy,intent?:string):StrategyPolicy{
 return {version:STRATEGY_POLICY_VERSION,mode:intent==='aggressive'?'distance':['conservative','layup'].includes(intent??'')?'control':personal.preference,explicit_turn:!!intent&&intent!=='default'};
}
export function systemRisk(row:{penalty_samples:number;bunker_samples:number;rough_samples:number;history_weight:number}){
 return row.penalty_samples*30+row.bunker_samples*4+row.rough_samples*.3+row.history_weight*20;
}
export function rankCandidates(rows:Candidate[],policy:StrategyPolicy,personal:PersonalStrategy,progress=true):Candidate|undefined{
 return [...rows].sort((a,b)=>{
  // Personal habits never trade away mapped penalty exposure or repeated local failures.
  const protectedRisk=a.penalty_samples-b.penalty_samples||a.history_weight-b.history_weight;
  if(protectedRisk)return protectedRisk;
  const risk=a.risk-b.risk;if(risk)return risk;
  const trust=(r:Candidate)=>policy.mode==='control'?(Number(r.club===personal.finder)*20+Number(personal.trusted_clubs.includes(r.club))*10):0;
  return (progress?(b.progress+trust(b))-(a.progress+trust(a)):b.width_yards-a.width_yards)||b.width_yards-a.width_yards;

 })[0];
}
export function chooseTee(rows:Candidate[],policy:StrategyPolicy,personal:PersonalStrategy){
 const driver=rankCandidates(rows.filter(r=>r.club==='一号木'),policy,personal);
 // System default values distance where penalty exposure has been checked; ordinary rough is not OB.
 if(policy.mode!=='control'&&driver&&driver.penalty_samples===0&&driver.history_weight===0)return driver;
 return rankCandidates(rows,policy,personal);
}
/** Compare all mapped clubs; a trusted club is preferred, never required. */
export function conservativeTee(rows:Candidate[],reference:Candidate|undefined,personal:PersonalStrategy,policy:StrategyPolicy){
 const noHigherHazard=(row:Candidate,against=reference)=>{
  if(!against)return true;
  if(row.penalty_samples>against.penalty_samples||row.history_weight>against.history_weight)return false;
  const fewerPenalties=row.penalty_samples<against.penalty_samples;
  const newPenaltyArea=(row.nearby??[]).some(k=>['water','ob'].includes(k)&&!(against.nearby??[]).includes(k));
  if(newPenaltyArea&&!fewerPenalties)return false;
  return row.bunker_samples<=against.bunker_samples||fewerPenalties||row.history_weight<against.history_weight;
 };

 const admissible=rows.filter(row=>noHigherHazard(row));
 const improved=(row:Candidate)=>!reference||row.risk<reference.risk||row.width_yards>reference.width_yards+3;
 const preferred=rankCandidates(admissible.filter(r=>r.club===personal.finder),policy,personal);
 const other=rankCandidates(admissible.filter(improved),policy,personal)??rankCandidates(admissible,policy,personal);
 const selected=preferred&&noHigherHazard(preferred,other)?preferred:other;
 return {selected,map_improved:selected?improved(selected):false};
}
