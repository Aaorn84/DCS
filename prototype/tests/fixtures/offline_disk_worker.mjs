import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {CheckpointStore} from '../../apps/mobile/src/checkpointStore.ts';
import {OfflineRound} from '../../apps/mobile/src/offlineRound.ts';
export const hash=async text=>createHash('sha256').update(text).digest('hex');
/** Host test adapter; it does not claim to implement Android/iOS storage durability. */
export function diskStore(directory,crash){
 fs.mkdirSync(directory,{recursive:true});
 const file=key=>path.join(directory,createHash('sha256').update(key).digest('hex'));
 const durable=(target,value)=>{const fd=fs.openSync(target,'w');try{fs.writeFileSync(fd,value);fs.fsyncSync(fd);}finally{fs.closeSync(fd);}};
 const die=()=>process.kill(process.pid,'SIGKILL');
 return {
  getItem:async key=>{try{return fs.readFileSync(file(key),'utf8');}catch(e){if(e.code==='ENOENT')return null;throw e;}},
  setItem:async(key,value)=>{
   const slot=/\.checkpoint\.[01]$/.test(key),head=key.endsWith('.checkpoint.head');
   if(slot&&crash==='slot-before'||head&&crash==='head-before')die();
   if(slot&&crash==='slot-partial'){durable(file(key),value.slice(0,Math.floor(value.length/2)));die();}
   const temporary=file(key)+'.tmp';durable(temporary,value);fs.renameSync(temporary,file(key));
   if(slot&&crash==='slot-after'||head&&crash==='head-after')die();
  },
  removeItem:async key=>{fs.rmSync(file(key),{force:true});}
 };
}
export function clientOnDisk(directory,crash){
 const store=new CheckpointStore(diskStore(directory,crash),hash,key=>key==='a');
 return new OfflineRound('https://offline.invalid','token',store,'a',()=> 'device-one',hash);
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
 globalThis.fetch=async()=>{throw Error('network disabled in terminated process');};
 const c=clientOnDisk(process.argv[2],process.argv[3]);await c.verifyCached();
 await c.turn('7号铁','selected-club','2026-01-01T00:00:01Z');
 throw Error('crash injection did not execute');
}
