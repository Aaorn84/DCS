import type {LocalStore} from './journeyPersistence.ts';

export class LocalPersistenceError extends Error {}

type Head={schema:1;revision:number;slot:0|1;sha256:string;deleted?:boolean};
/** Two-slot commit protocol. Requires atomic replacement of each small head value.
 * One shared instance per app process; this is not a multi-process database lock.
 * A damaged committed slot fails closed rather than silently losing an acknowledged shot.
 */
export class CheckpointStore implements LocalStore {
 private locks=new Map<string,Promise<void>>();
 private heads=new Map<string,Head|null>();
 constructor(private store:LocalStore,private sha256:(value:string)=>Promise<string>,private manages:(key:string)=>boolean){}
 private async serial<T>(key:string,work:()=>Promise<T>){
  const previous=this.locks.get(key)??Promise.resolve();let done!:()=>void;
  const current=new Promise<void>(resolve=>{done=resolve;});this.locks.set(key,current);
  await previous;try{return await work();}finally{done();if(this.locks.get(key)===current)this.locks.delete(key);}
 }
 private remember(key:string,head:Head|null){this.heads.delete(key);this.heads.set(key,head);if(this.heads.size>64)this.heads.delete(this.heads.keys().next().value!);}
 private async read(key:string):Promise<string|null>{
  const raw=await this.store.getItem(key+'.checkpoint.head');
  if(raw===null){this.remember(key,null);return null;}
  let head:Head;try{head=JSON.parse(raw);}catch{throw Error('本机提交标记损坏，请保留记录并联网核对。');}
  if(!head||typeof head!=='object'||head.schema!==1||!Number.isSafeInteger(head.revision)||head.revision<1||![0,1].includes(head.slot)||typeof head.sha256!=='string'||!/^[a-f0-9]{64}$/.test(head.sha256)||head.deleted!==undefined&&typeof head.deleted!=='boolean')throw Error('本机提交标记损坏，请保留记录并联网核对。');
  const value=await this.store.getItem(key+'.checkpoint.'+head.slot);
  if(value===null||await this.sha256(value)!==head.sha256||head.deleted&&value!=='')throw Error('本机已提交记录校验失败，请保留记录并联网核对；不会自动回退成绩。');
  this.remember(key,head);return head.deleted?null:value;
 }
 async getItem(key:string){if(!this.manages(key))return this.store.getItem(key);return this.serial(key,async()=>{try{return await this.read(key);}catch(error){this.heads.delete(key);throw error;}});}
 private async write(key:string,value:string|null){
  try{
   if(!this.heads.has(key))await this.read(key);
   const previous=this.heads.get(key),revision=(previous?.revision??0)+1;
   if(!Number.isSafeInteger(revision))throw Error('本机提交序号已超出支持范围，请保留记录。');
   const content=value??'';
   const head:Head={schema:1,revision,slot:previous?.slot===0?1:0,sha256:await this.sha256(content),...(value===null?{deleted:true}:{})};
   await this.store.setItem(key+'.checkpoint.'+head.slot,content);
   await this.store.setItem(key+'.checkpoint.head',JSON.stringify(head));
   this.remember(key,head);
  }catch(error){
   this.heads.delete(key);
   const full=/SQLITE_FULL|database.*full|disk.*full|storage.*full|ENOSPC|quota/i.test(String(error));
   throw new LocalPersistenceError(full?'本机存储空间不足，保存未确认。请释放空间后读取本机记录核对，再决定是否重试。':'本机保存未确认，请读取本机记录核对，再决定是否重试。',{cause:error});
  }
 }
 async setItem(key:string,value:string){if(!this.manages(key))return this.store.setItem(key,value);return this.serial(key,()=>this.write(key,value));}
 async removeItem(key:string){
  if(!this.manages(key)){if(this.store.removeItem)await this.store.removeItem(key);return;}
  return this.serial(key,()=>this.write(key,null));
 }
}
