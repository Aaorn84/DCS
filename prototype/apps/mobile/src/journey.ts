import type {JourneyPersistence} from './journeyPersistence.ts';
import {request, ApiError} from './api.ts';
export type Journey = {offline_protocol?:number;shared_core_version?:string;course_name?:string;simulation?:{hole:number;positions:{tee:Record<string,unknown>;fairway:Record<string,unknown>;green:Record<string,unknown>}};stage:string;distance_unit:string;version:number;question:string;choices:string[];quiet:boolean;memory_allowed:boolean|null;profile:Record<string,unknown>;round:any;history:unknown[];coach:{enabled:boolean;plan?:{focus:string}|null};score_summary:{confirmed_holes:number;confirmed_subtotal:number|null}};
export type JourneyResponse={journey:Journey;result?:{text:string;speak_allowed:boolean;pause?:boolean}};
/** Keep a lost request intact. A retry must use the same operation and event IDs. */
export class JourneyClient {
 pending:any=null;
 private saved:any={schema:1};
 private restored=false;
 constructor(public base:string,public token:string,private persistence?:JourneyPersistence,private endpoint='/journey',private scope:Record<string,unknown>={}){}
 async restore(){if(!this.restored){this.saved=await this.persistence?.read()??{schema:1};this.pending=this.saved.pending??null;this.restored=true;}return this.saved.snapshot as JourneyResponse|undefined;}
 private async persist(){try{if(this.persistence)await this.persistence.write({...this.saved,pending:this.pending});}catch(error){this.restored=false;throw error;}}
 async cachedSnapshot(){return this.restore();}
 async snapshot(action='snapshot'):Promise<JourneyResponse>{await this.restore();const reply=await request(this.base,this.endpoint,this.token,{...this.scope,action});this.saved.snapshot=reply;await this.persist();return reply;}
 async submit(event:Record<string,unknown>,operationId:string,version?:number):Promise<JourneyResponse>{
  await this.restore();
  if(this.pending)throw Error('上次请求回执未收到，请先重试原请求。');
  this.pending={...this.scope,action:this.endpoint==='/offline-rounds'?'event':'core_event',operation_id:operationId,event,expected_version:version};await this.persist();return this.retry();
 }
 async retry():Promise<JourneyResponse>{
  await this.restore();
  if(!this.pending)throw Error('没有待重试请求');
  const envelope=this.pending;
  try{const r=await request(this.base,this.endpoint,this.token,this.pending);this.saved.snapshot=r;this.pending=null;await this.persist();return r;}
  catch(e){if(e instanceof ApiError&&!e.retryable){this.pending=null;await this.persist();}else{this.pending=envelope;}throw e;}
 }
}
