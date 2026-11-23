/** Reversible storage-only deduplication; rule state and replay semantics do not change. */
export function encodeLocalState(model:any):any{
 if(!model)return model;
 const table:any[]=[],ids=new Map<string,number>();
 const hole=(h:any)=>({...h,rows:h.rows.map((row:any)=>{const key=JSON.stringify(row);let index=ids.get(key);if(index===undefined){index=table.length;ids.set(key,index);table.push(row);}return index;})});
 return {storage_codec:1,state:{...model,holes:Object.fromEntries(Object.entries(model.holes).map(([key,h])=>[key,hole(h)])),undo:model.undo.map((entry:any)=>({...entry,hole:hole(entry.hole)}))},rows:table};
}
export function decodeLocalState(saved:any):any{
 if(saved==null)return saved;
 if(saved.storage_codec!==1||!Array.isArray(saved.rows)||!saved.state?.holes||!Array.isArray(saved.state.undo))throw Error('本地规则存储格式损坏，请保留记录。');
 const hole=(h:any)=>({...h,rows:h.rows.map((index:any)=>{if(!Number.isInteger(index)||index<0||index>=saved.rows.length)throw Error('本地逐杆引用损坏，请保留记录。');return JSON.parse(JSON.stringify(saved.rows[index]));})});
 return {...saved.state,holes:Object.fromEntries(Object.entries(saved.state.holes).map(([key,h])=>[key,hole(h)])),undo:saved.state.undo.map((entry:any)=>({...entry,hole:hole(entry.hole)}))};
}
export function utf8Length(text:string):number{let bytes=0;for(const ch of text){const n=ch.codePointAt(0)!;bytes+=n<=0x7f?1:n<=0x7ff?2:n<=0xffff?3:4;}return bytes;}
