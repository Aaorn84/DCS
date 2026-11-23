import test from 'node:test';import assert from 'node:assert/strict';
import {encodeLocalState,decodeLocalState,utf8Length} from '../apps/mobile/src/localStateCodec.ts';
test('undo snapshots deduplicate rows without changing the replayable model',()=>{
 const rows=Array.from({length:80},(_,i)=>({id:'shot'+i,club:'5号木',origin:{latitude:22.7,longitude:114.15,accuracy_m:2},landing:null,active:true}));
 const model={holes:{'1':{rows,score:null}},undo:Array.from({length:20},()=>({hole_number:1,hole:{rows:structuredClone(rows),score:null},context:{hole:1}})),revision:80,receipts:{}};
 const encoded=encodeLocalState(model);assert.deepEqual(decodeLocalState(encoded),model);assert.ok(utf8Length(JSON.stringify(encoded))<utf8Length(JSON.stringify(model))/4);encoded.state.holes['1'].rows[0]=99999;assert.throws(()=>decodeLocalState(encoded),/引用损坏/);
});
test('UTF8 size protection counts Chinese and supplementary characters accurately',()=>{assert.equal(utf8Length('a球🏌'),Buffer.byteLength('a球🏌','utf8'));});
test('raw prior state documents are rejected instead of silently decoded',()=>{
 assert.throws(()=>decodeLocalState({holes:{},undo:[],revision:0}),/存储格式损坏/);assert.equal(decodeLocalState(undefined),undefined);
});
