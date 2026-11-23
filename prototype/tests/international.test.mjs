import test from 'node:test';
import assert from 'node:assert/strict';
import {InternationalClient} from '../apps/mobile/src/international.ts';
import {voiceLocale,speechHints} from '../apps/mobile/src/locale.ts';
test('voice locales have distinct golf vocabulary and no silent fallback',()=>{
 for(const locale of ['zh-CN','en-US','en-GB','ja-JP','ko-KR','es-ES','pt-PT','de-DE','fr-FR','it-IT']){assert.equal(voiceLocale(locale),locale);assert.ok(speechHints[locale].length);}
 assert.throws(()=>voiceLocale('nl-NL'),/Unsupported/);
 assert.notDeepEqual(speechHints['ja-JP'],speechHints['ko-KR']);
});
test('international client retries the exact authenticated semantic envelope',async()=>{
 const previous=globalThis.fetch,bodies=[];let first=true;
 globalThis.fetch=async(url,init)=>{assert.ok(url.endsWith('/international'));assert.equal(init.headers.Authorization,'Bearer test');bodies.push(init.body);if(first){first=false;throw Error('lost');}return new Response(JSON.stringify({version:1}),{status:200});};
 try{const c=new InternationalClient('http://example.test','test');await assert.rejects(c.submit({type:'semantic',event_id:'e1',candidate:{type:'execution_report',slots:{club:'7i'}}},'op1',0));assert.ok(c.pending);await c.retry();assert.equal(bodies[0],bodies[1]);assert.equal(c.pending,null);}finally{globalThis.fetch=previous;}
});
test('international client does not retry a stale semantic answer after conflict',async()=>{
 const previous=globalThis.fetch;
 globalThis.fetch=async()=>new Response(JSON.stringify({error:'stale'}),{status:409});
 try{const c=new InternationalClient('http://example.test','test');await assert.rejects(c.submit({type:'configure'},'op'));assert.equal(c.pending,null);await assert.rejects(c.retry(),/No pending/);}finally{globalThis.fetch=previous;}
});
test('temporary HTTP failures retain the original international operation',async()=>{
 const previous=globalThis.fetch;
 try{
  for(const status of [408,425,429,500,502,503,504]){
   const bodies=[];globalThis.fetch=async(_u,init)=>{bodies.push(init.body);return new Response(JSON.stringify({error:'temporary'}),{status})};
   const c=new InternationalClient('https://example.test','token');await assert.rejects(c.submit({type:'semantic',event_id:'original'},'same-operation',4));assert.ok(c.pending,status);
   globalThis.fetch=async(_u,init)=>{bodies.push(init.body);return new Response(JSON.stringify({version:5}),{status:200})};
   await c.retry();assert.equal(bodies[0],bodies[1]);assert.equal(c.pending,null);
  }
 }finally{globalThis.fetch=previous;}
});
