import test from 'node:test';
import assert from 'node:assert/strict';
import {JourneyClient} from '../apps/mobile/src/journey.ts';
test('lost journey receipt retries exactly the original envelope',async()=>{
 const previous=globalThis.fetch, bodies=[];let first=true;
 globalThis.fetch=async(_url,init)=>{bodies.push(init.body);if(first){first=false;throw Error('lost response')}return new Response(JSON.stringify({journey:{stage:'name'}}),{status:200,headers:{'Content-Type':'application/json'}})};
 try{const c=new JourneyClient('http://example.test','test-token');await assert.rejects(c.submit({type:'message',event_id:'e',text:'可以记住'},'op',0));assert.ok(c.pending);await c.retry();assert.equal(bodies[0],bodies[1]);assert.equal(c.pending,null)}finally{globalThis.fetch=previous}
});
test('a server version conflict clears retry rather than resending a stale answer',async()=>{
 const previous=globalThis.fetch;
 globalThis.fetch=async()=>new Response(JSON.stringify({error:'version conflict'}),{status:409,headers:{'Content-Type':'application/json'}});
 try{const c=new JourneyClient('http://example.test','test-token');await assert.rejects(c.submit({type:'message',event_id:'e',text:'阿明'},'op',0));assert.equal(c.pending,null);await assert.rejects(c.retry(),/没有待重试/)}finally{globalThis.fetch=previous}
});
