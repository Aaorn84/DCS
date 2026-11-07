import {request, ApiError} from './api.ts';
export type Journey = {course_name?:string;simulation?:{hole:number;positions:{tee:Record<string,unknown>;fairway:Record<string,unknown>;green:Record<string,unknown>}};stage:string;distance_unit:string;version:number;question:string;choices:string[];quiet:boolean;memory_allowed:boolean|null;profile:Record<string,unknown>;round:any;history:unknown[];coach:{enabled:boolean;plan?:{focus:string}|null};score_summary:{confirmed_holes:number;confirmed_subtotal:number|null}};
export type JourneyResponse={journey:Journey;result?:{text:string;speak_allowed:boolean;pause?:boolean}};
/** Keep a lost request intact. A retry must use the same operation and event IDs. */
export class JourneyClient {
 pending:any=null;
 constructor(public base:string,public token:string){}
 snapshot(action='snapshot'):Promise<JourneyResponse>{return request(this.base,'/journey',this.token,{action});}
 async submit(event:Record<string,unknown>,operationId:string,version?:number):Promise<JourneyResponse>{
  if(this.pending)throw Error('上次请求回执未收到，请先重试原请求。');
  this.pending={action:'event',operation_id:operationId,event,expected_version:version};return this.retry();
 }
 async retry():Promise<JourneyResponse>{
  if(!this.pending)throw Error('没有待重试请求');
  try{const r=await request(this.base,'/journey',this.token,this.pending);this.pending=null;return r;}
  catch(e){if(e instanceof ApiError)this.pending=null;throw e;}
 }
}
