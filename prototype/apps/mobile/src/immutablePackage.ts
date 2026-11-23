import type {LocalStore} from './journeyPersistence.ts';
/** Small immutable rows avoid native storage per-value limits. Never split a surrogate pair. */
const CHARS=65536,MAX_PARTS=256;
export async function savePackage(store:LocalStore,key:string,pack:any){
 const {package:parsed,...wire}=pack;const raw=JSON.stringify(wire);let parts=0;
 for(let start=0;start<raw.length;){let end=Math.min(start+CHARS,raw.length);const code=raw.charCodeAt(end-1);if(end<raw.length&&code>=0xd800&&code<=0xdbff)end--;
  if(parts>=MAX_PARTS)throw Error('本场离线资料过大，请缩减地图包或历史摘要后再准备。');
  await store.setItem(key+'.part.'+parts,raw.slice(start,end));parts++;start=end;
 }
 await store.setItem(key,JSON.stringify({storage_format:1,parts}));
}
export async function loadPackage(store:LocalStore,key:string){
 const raw=await store.getItem(key);if(!raw)throw Error('本场离线包缺失，请保留记录并联网核对。');const saved=JSON.parse(raw);
 if(saved.storage_format===1){
  if(!Number.isInteger(saved.parts)||saved.parts<1||saved.parts>MAX_PARTS)throw Error('本场离线包分段信息损坏。');
  const chunks=[];for(let n=0;n<saved.parts;n++){const chunk=await store.getItem(key+'.part.'+n);if(chunk===null)throw Error('本场离线包分段缺失，请保留记录。');chunks.push(chunk);}
  const pack=JSON.parse(chunks.join(''));if(typeof pack.payload_json!=='string')throw Error('离线包内容缺失。');pack.package=JSON.parse(pack.payload_json);return pack;
 }
 throw Error('不支持旧离线包存储格式，请重置过期测试数据。');
}
export async function removePackage(store:LocalStore,key:string){
 if(!store.removeItem)return;const raw=await store.getItem(key);if(raw){const saved=JSON.parse(raw);if(saved.storage_format===1&&Number.isInteger(saved.parts)&&saved.parts>0&&saved.parts<=MAX_PARTS)for(let n=0;n<saved.parts;n++)await store.removeItem(key+'.part.'+n);}
 await store.removeItem(key);
}
