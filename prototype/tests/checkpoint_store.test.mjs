import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {CheckpointStore} from '../apps/mobile/src/checkpointStore.ts';
const hash=async text=>createHash('sha256').update(text).digest('hex');
function fixture(){const rows=new Map();let failure;const store={getItem:async k=>rows.get(k)??null,setItem:async(k,v)=>{if(failure?.(k,v))throw Error('storage full');rows.set(k,v);},removeItem:async k=>{rows.delete(k);}};return {rows,store,fail:fn=>failure=fn,make:()=>new CheckpointStore(store,hash,key=>!key.includes('.package.'))};}
test('flat legacy documents are ignored rather than migrated',async()=>{
 const f=fixture();f.rows.set('a','old');const c=f.make();assert.equal(await c.getItem('a'),null);await c.setItem('a','new');assert.equal(f.rows.get('a'),'old');assert.equal(await f.make().getItem('a'),'new');
});
test('storage pressure at slot or head write preserves the previous committed document',async()=>{
 for(const suffix of ['.checkpoint.1','.checkpoint.head']){
  const f=fixture();const c=f.make();await c.setItem('a','old');f.fail(k=>k.endsWith(suffix));await assert.rejects(c.setItem('a','new'),/存储空间不足/);assert.equal(await f.make().getItem('a'),'old');
  f.fail();await c.setItem('a','new');assert.equal(await f.make().getItem('a'),'new');
 }
});
test('uncommitted partial slots are ignored and corrupted committed data never silently rolls back',async()=>{
 const f=fixture(),c=f.make();await c.setItem('a','old');await c.setItem('a','new');f.rows.set('a.checkpoint.0','partial');assert.equal(await f.make().getItem('a'),'new');
 f.rows.set('a.checkpoint.1','corrupt');await assert.rejects(f.make().getItem('a'),/不会自动回退/);
});
test('damaged head fails closed and uncommitted first slots do not revive flat documents',async()=>{
 const f=fixture();f.rows.set('a','legacy');f.rows.set('a.checkpoint.0','partial');assert.equal(await f.make().getItem('a'),null);
 f.rows.set('a.checkpoint.head','{');await assert.rejects(f.make().getItem('a'),/提交标记损坏/);
});
test('account isolation, concurrent writers, deletion and bounded slot retention',async()=>{
 const f=fixture(),c=f.make();await Promise.all(Array.from({length:80},(_,i)=>c.setItem('a',String(i))));assert.equal(await f.make().getItem('a'),'79');assert.equal(f.rows.size,3);
 await c.setItem('b','other');await c.removeItem('a');assert.equal(await f.make().getItem('a'),null);assert.equal(await f.make().getItem('b'),'other');await c.setItem('a','again');assert.equal(await f.make().getItem('a'),'again');
});
test('immutable packages bypass checkpoints to avoid duplicating map bytes',async()=>{
 const f=fixture(),c=f.make();await c.setItem('a.package.digest','map');assert.deepEqual([...f.rows.keys()],['a.package.digest']);await c.removeItem('a.package.digest');assert.equal(f.rows.size,0);
});
