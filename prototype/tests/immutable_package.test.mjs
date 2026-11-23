import test from 'node:test';import assert from 'node:assert/strict';
import {savePackage,loadPackage,removePackage} from '../apps/mobile/src/immutablePackage.ts';
function fixture(){const rows=new Map();return {rows,store:{getItem:async k=>rows.get(k)??null,setItem:async(k,v)=>rows.set(k,v),removeItem:async k=>rows.delete(k)}};}
test('large immutable packages are chunked without duplicating parsed map or splitting Unicode',async()=>{
 const {rows,store}=fixture();const parsed={map:'x'.repeat(65500)+'🏌️'.repeat(40000)};const pack={package:parsed,payload_json:JSON.stringify(parsed),sha256:'digest',source_version:1};
 await savePackage(store,'pack',pack);const result=await loadPackage(store,'pack');assert.deepEqual(result,pack);for(const [key,value] of rows)if(key.includes('.part.'))assert.ok(Buffer.byteLength(value)<=262144);assert.ok([...rows.values()].reduce((n,v)=>n+Buffer.byteLength(v),0)<Buffer.byteLength(JSON.stringify(pack))*.6);await removePackage(store,'pack');assert.equal(rows.size,0);
});
test('an incomplete or damaged immutable package is never accepted',async()=>{
 const {rows,store}=fixture();await savePackage(store,'pack',{package:{a:1},payload_json:'{"a":1}',sha256:'digest'});rows.delete('pack.part.0');await assert.rejects(loadPackage(store,'pack'),/分段缺失/);rows.set('pack','{"storage_format":1,"parts":9999}');await assert.rejects(loadPackage(store,'pack'),/分段信息损坏/);
});
test('flat old package records are rejected instead of read through',async()=>{
 const {rows,store}=fixture();rows.set('pack',JSON.stringify({package:{course:'old'},payload_json:'{}'}));await assert.rejects(loadPackage(store,'pack'),/旧离线包存储格式/);
});
