import {request,ApiError} from './api.ts';
import type {RegionalPreferences} from './locale.ts';
export type SemanticCandidate={type:'fact_request'|'player_intent'|'decision_commitment'|'execution_report'|'shot_outcome'|'feel_or_cause'|'correction'|'score_report'|'state_transition'|'interaction_override'|'companion_dialogue'|'profile_answer'|'confirmation';slots:Record<string,unknown>;confidence?:number;alternatives?:SemanticCandidate[]};
export type InternationalResponse={configuration:RegionalPreferences;journey:{stage:string;version:number;[key:string]:unknown};version:number;capabilities:Record<string,unknown>;result?:{text:string;speak_allowed:boolean;status?:string;source_text?:string;[key:string]:unknown}};
/** Separate aggregate from the legacy Chinese demo. Same authentication and engine. */
export class InternationalClient {
 pending:Record<string,unknown>|null=null;
 constructor(public base:string,public token:string){}
 snapshot(action:'snapshot'|'replay'='snapshot'):Promise<InternationalResponse>{return request(this.base,'/international',this.token,{action});}
 async submit(event:Record<string,unknown>,operationId:string,version?:number):Promise<InternationalResponse>{
  if(this.pending)throw Error('Retry the pending request first.');
  this.pending={action:'event',operation_id:operationId,event,expected_version:version};return this.retry();
 }
 async retry():Promise<InternationalResponse>{
  if(!this.pending)throw Error('No pending request.');
  try{const result=await request(this.base,'/international',this.token,this.pending);this.pending=null;return result;}
  catch(error){if(error instanceof ApiError)this.pending=null;throw error;}
 }
}
