import test from 'node:test';
import assert from 'node:assert/strict';
import {empty, edit, acknowledge, merge, resolveConflict, score, recap} from '../apps/mobile/src/domain.ts';
const data = {text:'先让我安静一下',source:'user_confirmed'};
test('offline edits chain versions and acknowledgements never overwrite newer local data',()=>{
  let s=edit(empty(),'memory','m',data,'one');
  s=edit(s,'memory','m',{...data,text:'新内容'},'two');
  assert.deepEqual(s.pending.map(o=>o.baseVersion),[0,1]);
  s=acknowledge(s,s.pending[0],{id:'m',kind:'memory',version:1,deleted:false,data});
  assert.equal(s.records[0].data.text,'新内容');
  s=merge(s,[{id:'m',kind:'memory',version:1,deleted:false,data}]);
  assert.equal(s.records[0].data.text,'新内容');
});
test('conflict resolution drops superseded operations and rebases latest local value',()=>{
  let s=edit(empty(),'memory','m',data,'one');
  s=edit(s,'memory','m',{...data,text:'new'},'two');
  s=resolveConflict(s,{kind:'memory',id:'m'},{kind:'memory',id:'m',version:8,deleted:false,data},true,'rebase');
  assert.equal(s.pending.length,1);assert.equal(s.pending[0].baseVersion,8);
  assert.equal(s.pending[0].data.text,'new');
});
test('server deletion cannot be overridden by stale device',()=>{
  let s=edit(empty(),'memory','m',data,'one');
  s=resolveConflict(s,{kind:'memory',id:'m'},{kind:'memory',id:'m',version:2,deleted:true,data:{}},true,'retry');
  assert.equal(s.pending.length,0);assert.equal(s.records[0].deleted,true);
  assert.throws(()=>edit(s,'memory','m',data,'restore'));
});
test('delete clears transient context and a partial round never counts penalties twice',()=>{
  let s=edit(empty(),'memory','m',data,'one');s.chat=[{role:'assistant',text:data.text}];
  s=edit(s,'memory','m',data,'delete',true);assert.deepEqual(s.chat,[]);assert.deepEqual(s.records[0].data,{});
  const r=recap({course:'test',status:'finished',scores:[score(6,1,2),...Array(17).fill(null)]});
  assert.deepEqual(r,{holes:1,total:6,penalty:1,putts:2});
  assert.throws(()=>score(4,3,2));assert.throws(()=>score(4.2,0,0));
});
