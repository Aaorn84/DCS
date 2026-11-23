import {parseStrategyPreference} from '../../../shared/core/personalStrategy.ts';
import type {SetupDraft} from './courseLibrary.ts';
import {normalizeClub} from '../../../shared/core/bag.ts';
import {setupProfile} from '../../../shared/core/offlineSetup.ts';
const prompts:Record<string,string>={memory:'你愿意让我跨场记住球杆和偏好吗？也可以仅用于本场。',name:'怎么称呼你？可以跳过。',proactive:'上一洞还没记分时，可以轻问一句吗？',shot_recording:'是否愿意记录逐杆信息？',driver:'一号木Carry大概多少？不知道可以跳过。',seven:'7号铁Carry大概多少？不知道可以跳过。',miss:'平时更常偏左、偏右，还是不固定？',finder:'哪支是最信任的保底开球杆？可一起报Carry，也可以跳过。',course:'选择已下载的球场，或先联网下载。',tee:'选择已下载的Tee。',start_hole:'从第几洞开始？',ready:'本机资料已准备，确认球场、Tee和起始洞后即可开局。'};
export function setupPrompt(d:SetupDraft){return prompts[d.stage]??prompts.course;}
export function setupChoices(d:SetupDraft){return ({memory:['可以记住','仅本场'],name:['跳过'],proactive:['可以提醒','你叫我再说'],shot_recording:['可以记录','不记录击球'],driver:['跳过'],seven:['跳过'],miss:['偏右','偏左','不固定','跳过'],finder:['跳过'],start_hole:['1','10']} as Record<string,string[]>)[d.stage]??[];}
export function setupAnswer(original:SetupDraft,input:string):{draft:SetupDraft;text:string}{
 const d=JSON.parse(JSON.stringify(original)) as SetupDraft,text=input.trim(),clean=text.replace(/[\s，,。]/g,'');
 const preference=parseStrategyPreference(text);if(preference){d.patch.strategy_preference=preference;return {draft:d,text:'已在本机保存长期策略偏好。'+setupPrompt(d)};}
 const pattern=/(一号木|1号木|[3-9]号木|(?:[2-9]号)?铁木杆|[2-9]号铁|P杆|[4-6]\d度杆)\s*(\d{1,3})(?:\s*(?:到|[-–~])\s*(\d{1,3}))?\s*(码|米)?/g;
 const carries=[...text.matchAll(pattern)];const rest=text.replace(pattern,'').replace(/[\s，,、；;。]/g,'');
 if(carries.length&&rest===''){for(const m of carries){const scale=m[4]==='米'?1/.9144:1;d.patch.carries={...d.patch.carries,[normalizeClub(m[1])]:{low:Number(m[2])*scale,high:Number(m[3]??m[2])*scale}};}if(d.stage==='finder')d.patch.finder=normalizeClub(carries[0][1]);setupProfile({},d.patch);d.stage=d.stage==='driver'?'seven':d.stage==='seven'?'miss':d.stage==='finder'?'course':d.stage;return {draft:d,text:'球杆Carry已在本机保存。'+setupPrompt(d)};}
 if(clean==='先打球'||clean==='先打球，稍后了解'||clean==='先打球稍后了解'){d.stage='course';return {draft:d,text:setupPrompt(d)};}
 if(clean==='关闭跨场记忆'||clean==='不跨场保存'){d.memory_allowed=false;delete d.patch.strategy_usage;return {draft:d,text:'本机资料仅用于本场。'+setupPrompt(d)};}if(clean==='允许跨场记忆'){d.memory_allowed=true;return {draft:d,text:'已允许跨场使用你确认的资料。'+setupPrompt(d)};}
 const next=(stage:string)=>{d.stage=stage;setupProfile({},d.patch);return {draft:d,text:setupPrompt(d)};};
 if(d.stage==='memory'){if(/^(?:仅本场|不要|不愿意|不记住|跳过)$/.test(clean)){d.memory_allowed=false;return next('name');}if(/^(?:可以|愿意|可以记住|记住)$/.test(clean)){d.memory_allowed=true;return next('name');}}
 else if(d.stage==='name'){if(clean!=='跳过')d.patch.name=text.slice(0,40);return next('proactive');}
 else if(d.stage==='proactive'){if(!/^(可以|好|可以提醒|你叫我再说|不要|跳过)$/.test(clean))return {draft:d,text:setupPrompt(d)};d.patch.proactive=/^(可以|好|可以提醒)$/.test(clean);return next('shot_recording');}
 else if(d.stage==='shot_recording'){if(!/^(可以|好|可以记录|不记录击球|不要|跳过)$/.test(clean))return {draft:d,text:setupPrompt(d)};d.patch.shot_recording=/^(可以|好|可以记录)$/.test(clean);return next('driver');}
 else if(d.stage==='driver'||d.stage==='seven'){
  if(/^\d{1,3}(?:码|米)?$/.test(clean))return setupAnswer(d,(d.stage==='driver'?'一号木':'7号铁')+clean);
  if(/跳过|不知道/.test(clean))return next(d.stage==='driver'?'seven':'miss');
 }else if(d.stage==='miss'){if(clean!=='跳过')d.patch.usual_miss=text.slice(0,100);return next('finder');}
 else if(d.stage==='finder'){if(clean==='跳过')return next('course');const club=normalizeClub(clean);if(/^(一号木|[3-9]号木|(?:[2-9]号)?铁木杆|[2-9]号铁)$/.test(club)){d.patch.finder=club;return next('course');}}
 else if(d.stage==='start_hole'&&/^\d{1,2}$/.test(clean)){const n=Number(clean);if(n>=1&&n<=18){d.start_hole=n;return next('ready');}}
 return {draft:d,text:setupPrompt(d)};
}
