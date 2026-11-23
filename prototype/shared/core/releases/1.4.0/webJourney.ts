/** Web transport/presentation adapter. All golf mutations go through roundEngine. */
import {createLocalRound,applyLocalCommand,CoreRuleError} from './roundEngine.ts';
import {parseLocalTurn,localChoices,readGolfNumber} from './dialogue.ts';
import {planStrategy} from './strategy.ts';
import {bag} from './bag.ts';
import {CORE_VERSION} from './protocol.ts';
import {distance,surfaces,classifyLocation,validPoint} from './geometry.ts';
export function webJourneyTurn(pack:any,original:any,event:any,saved:any={}){
 let model=original??createLocalRound(pack),context=JSON.parse(JSON.stringify(saved??{}));
 let text='',flags:any={},strategy:any,commands:any[]=[];
 const add=(command:string,data:any={})=>commands.push({command,data});
 const apply=()=>{for(const [i,cmd] of commands.entries())model=applyLocalCommand(model,{v:1,semantics:2,id:event.event_id+'-'+i,at:event.observed_at,expected_revision:model.revision,...cmd});};
 if(model.round_id!==pack.round.id||model.core_version!==CORE_VERSION)throw new CoreRuleError('shared web round mismatch');
 const current=()=>model.holes[String(model.hole)],last=()=>[...current().rows].reverse().find((r:any)=>r.kind==='stroke'&&r.active);
 const hole=()=>pack.course.holes.find((h:any)=>h.number===model.hole);
 const query=/怎么打|如何打|风险|其他.*(?:方案|路线|策略)|其它.*(?:方案|路线|策略)|保守|稳一点|稳妥|安全.*(?:方案|策略)|分两杆|过渡|想打短一点/;
 const message=String(event.text??'').trim(),clean=message.replace(/[\s，,。！？!?]/g,'');
 const oldRevision=model.revision;
 const advice=context.advice?.revision===model.revision?context.advice.plan:null;
 function plan(followup=false){
  const kind=/保守|安全|稳一点|稳妥/.test(message)?'conservative':/过渡|分两杆|打短一点/.test(message)?'layup':/其他|其它/.test(message)?'alternative':'default';
  const intent=followup&&context.advice?.intent?context.advice.intent:{kind,...(kind==='alternative'&&advice?.options?.[0]?{exclude_club:advice.options[0].club}:{})};
  const key=JSON.stringify(intent);
  if(context.advice?.revision===model.revision&&context.advice.intent_key===key){strategy=context.advice.plan;flags.strategy_cache_hit=true;}
  else{strategy=planStrategy(pack,model,intent);context.advice={revision:model.revision,plan:strategy,intent,intent_key:key};flags.strategy_cache_hit=false;}
  return strategy.text;
 }
 function riskPrompt(){
  const r=last();if(!r?.landing||model.pending)return '';
  const kind=classifyLocation(hole(),pack.course.reference_simulation===true,surfaces(hole(),pack.course.reference_simulation===true),r.landing);
  if(['water','ob'].includes(kind)&&!current().incidents.some((i:any)=>i.stroke_id===r.id)){
   const p=planStrategy(pack,model);if(p.question==='ball_outcome'){context.advice={revision:model.revision,plan:p};return p.text;}
  }return '';
 }
 if(event.type==='simulation_hole'){
  if(model.stage!=='playing')throw new CoreRuleError('start round first');
  const old=model.hole,hasShots=current().rows.some((r:any)=>r.kind==='stroke'&&r.active);
  add('navigate_hole',{hole:event.hole});
  const tee=pack.course.holes.find((h:any)=>h.number===event.hole)?.simulation_positions?.tee;
  if(tee)add('set_position',{point:{latitude:tee.latitude,longitude:tee.longitude,accuracy_m:tee.accuracy_m??2}});apply();
  // Use unique event ids across the two portions of this single atomic server event.
  flags.simulation_hole_switched=true;context.audio={enabled:false,phase:'idle'};context.awaitingLanding=false;
  if(old!==model.hole&&hasShots&&!model.holes[String(old)].score){context.scoreDue=old;text=`第${old}洞还没记分，刚才一共几杆？`;}
 }else if(event.type==='gps'){
  if(model.stage!=='playing')return {model:original,context,text:'请先开始本场球局，再采用地图位置。',flags:{ignored:true,reason:'start_round_first'},choices:localChoices(model),carry:bag(model.profile)};
  const data=event.data??{},point={latitude:data.latitude,longitude:data.longitude,accuracy_m:data.accuracy_m};
  if(!validPoint(point))throw new CoreRuleError('invalid position');
  if(data.simulation_hole!=null&&data.simulation_hole!==model.hole)throw new CoreRuleError('map point belongs to another hole');
  const action=data.simulation_position_action??'move';
  if(data.simulation_refresh&&model.position&&distance(model.position,point)<.01)return {model,context,text:'',flags:{ignored:false},choices:localChoices(model),carry:bag(model.profile)};
  if(action==='shot'){
   if(model.pending)throw new CoreRuleError('resolve ball first');
   const r=last(),completeExisting=context.awaitingLanding&&r&&!r.landing&&!model.selection;
   const lie=classifyLocation(hole(),pack.course.reference_simulation===true,surfaces(hole(),pack.course.reference_simulation===true),point),actualLie=['green','fairway','bunker'].includes(lie)?lie:'unknown';
   if(completeExisting)add('set_landing',{point,lie:actualLie});
   else add('record_stroke',{landing:point,lie:actualLie});
   apply();context.awaitingLanding=false;flags.simulated_shot_recorded=!completeExisting;text=riskPrompt();
  }else if(action==='correct'){
   add('set_landing',{point});apply();text=riskPrompt();
  }else if(action==='move'){
   add('set_position',{point});apply();
  }else throw new CoreRuleError('unsupported map position action');
 }else if(event.type==='resume'){
  text=model.stage==='ready'?'准备好了，可以开始本场球局。':'已恢复本场共用核心记录。';
 }else if(event.type==='message'){
  if(clean==='安静'){context.quiet=true;text='';}
  else if(clean==='继续'){context.quiet=false;text='我在，需要建议时叫我。';}
  else if(clean==='开启击球声音识别'){context.audio={enabled:true,phase:model.selection?'armed':'idle',arm_id:model.selection?.event_id??null,delay_seconds:5};text='已开启击球声音识别。';}
  else if(clean==='关闭击球声音识别'){context.audio={enabled:false,phase:'idle'};text='已关闭击球声音识别。';}
  else if(clean==='音频检测到疑似击球'){
   if(context.quiet||context.audio?.enabled!==true||context.audio?.phase!=='armed'||!model.selection)throw new CoreRuleError('select a club before impact');
   add('record_stroke');apply();context.awaitingLanding=true;context.audio={...context.audio,phase:'waiting',delay_seconds:5};text='';
  }else if(clean==='击球声音等待结束'){
   if(context.audio?.phase==='waiting'){context.audio={enabled:false,phase:'idle'};text='看到球落哪儿了吗？';}
  }else if(/^(?:到发球台了|到发球台)$/.test(clean)){
   const green=hole().objects?.find((o:any)=>o.kind==='green_center');text=model.position&&green?`第${model.hole}洞，${hole().par}杆洞。到果岭参考点直线约${Math.round(distance(model.position,green)/.9144/5)*5}码，不是旗杆距离。`:'请先更新球位。';
  }else if(/还有多少|到果岭多少|距离多少/.test(message)){
   const green=hole().objects?.find((o:any)=>o.kind==='green_center'),unit=model.profile.units?.value==='米'?'米':'码';text=model.position&&green?`到果岭参考点直线约${Math.round(distance(model.position,green)/(unit==='米'?1:.9144))}${unit}，不是旗杆距离。`:'请先更新到实际球位，再询问距离。';
  }else if(clean==='没有罚杆'&&model.draft){text='按已登记的'+model.draft.penalties+'杆罚杆核对，总杆已包含罚杆。确认记录吗？';}
  else if(!model.pending&&!model.draft&&model.stage==='playing'&&(/^(?:这洞|本洞)?([0-9一二两三四五六七八九十]{1,2})杆$/.test(clean)||context.partialScore&&/^([0-9一二两三四五六七八九十]{1,2})推$/.test(clean))){
   const totalMatch=clean.match(/^(?:这洞|本洞)?([0-9一二两三四五六七八九十]{1,2})杆$/),puttMatch=clean.match(/^([0-9一二两三四五六七八九十]{1,2})推$/);
   if(totalMatch)context.partialScore={hole:Number(context.scoreDue??model.hole),total:readGolfNumber(totalMatch[1])};
   const pending=context.partialScore,h=model.holes[String(pending.hole)],penalties=h.rows.filter((r:any)=>r.kind==='penalty'&&r.active).reduce((n:number,r:any)=>n+r.amount,0),end=[...h.rows].reverse().find((r:any)=>r.kind==='stroke'&&r.active);
   const nonPutts=h.rows.filter((r:any)=>r.kind==='stroke'&&r.active&&r.is_putt!==true).length;
   const putts=puttMatch?readGolfNumber(puttMatch[1]):end?.lie==='green'?pending.total-nonPutts-penalties:null;
   if(putts!==null){add('draft_score',{hole:pending.hole,total:pending.total,putts,penalties});apply();delete context.partialScore;text=(puttMatch?'':'按已记击球推算，')+`第${pending.hole}洞${pending.total}杆，${putts}推，罚杆${penalties}。确认记录吗？`;}
   else text=`第${pending.hole}洞几推？可以说“两推”；未确认前不会计入成绩。`;
  }
  else if(query.test(message)&&!model.pending&&!model.draft&&model.stage==='playing')text=plan();
  else{
   let input=message;
   if(advice?.question==='pin'&&/^(跳过|不知道)$/.test(clean))input='跳过旗位';
   if(advice?.question==='fairway_carry'&&/^(跳过|不知道|没有)$/.test(clean))input=clean==='没有'?'没有球道木和铁木杆':'跳过球道杆距';
   if(advice?.question==='finder_carry'&&/^\d{1,3}(?:码|米)?$/.test(clean))input=advice.missing_club+clean;
   if(/^(按这个打|就按这个打|好)$/.test(clean)&&advice?.options?.length===1)input=advice.options[0].club;
   let result=parseLocalTurn(model,input);
   if(advice?.question==='ball_outcome'&&/^(确认在界内|确认出界|确认OB|确认下水)$/i.test(clean)){
    result=parseLocalTurn({...model,pending:{phase:'uncertain',cause:advice.suspected}},input);result.commands.unshift({command:'report_incident',data:{cause:advice.suspected}});
   }
   // A pending previous-hole score belongs to that hole, not the new tee.
   if(context.scoreDue&&!model.draft&&!result.commands.some((c:any)=>c.command==='draft_score'&&c.data.hole!=null)){
    const due=Number(context.scoreDue),scoreModel={...model,hole:due};let scoring=parseLocalTurn(scoreModel,input);
    const totalOnly=clean.match(/^(?:这洞|本洞)?(\d{1,2})杆?$/);
    if(totalOnly){const h=model.holes[String(due)],nonPutts=h.rows.filter((r:any)=>r.kind==='stroke'&&r.active&&r.is_putt!==true).length,penalties=h.rows.filter((r:any)=>r.kind==='penalty'&&r.active).reduce((n:number,r:any)=>n+r.amount,0),end=[...h.rows].reverse().find((r:any)=>r.kind==='stroke'&&r.active);
     if(end?.lie==='green'){const putts=Number(totalOnly[1])-nonPutts-penalties;if(putts>=0)scoring=parseLocalTurn(scoreModel,`${totalOnly[1]}杆${putts}推`);}
     else{text='请合并报告第'+due+'洞总杆和推杆，例如“六杆两推”；不会把未知推杆猜成已确认。';}
    }
    if(scoring.commands.some((c:any)=>c.command==='draft_score')){result=scoring;for(const cmd of result.commands)if(cmd.command==='draft_score')cmd.data.hole=due;}
    else if(totalOnly)return {model,context,text,flags,choices:['这洞四杆两推','这洞六杆两推'],carry:bag(model.profile)};
   }
   for(const cmd of result.commands)if(cmd.command==='select_club'){const target=advice?.options?.find((o:any)=>o.club===cmd.data.club);if(target)cmd.data.target=target.aim_point;}
   commands=result.commands;text=result.text;apply();
   if(commands.some(c=>c.command==='confirm_score')){delete context.scoreDue;delete context.partialScore;}
   if(commands.some(c=>c.command==='record_stroke'))context.awaitingLanding=true;
   if(commands.some(c=>c.command==='select_club')&&context.audio?.enabled)context.audio={enabled:true,phase:'armed',arm_id:model.selection.event_id,delay_seconds:5};
   if(model.revision!==oldRevision&&advice?.question&&commands.every(c=>['set_pin','set_lie','set_club_carry','set_fairway_carry_status','set_club_purpose'].includes(c.command)))text+=plan(true);
  }
 }else throw new CoreRuleError('unsupported shared web event');
 if(commands.some(c=>c.command==='confirm_finish'))text='本场已收好，需要我给本场做个分析总结吗？';
 let choices=localChoices(model);
 if(context.partialScore&&!model.draft)choices=['一推','两推','三推'];
 if(strategy?.question==='pin')choices=['左前','中部','右后','跳过旗位'];
 if(strategy?.question==='ball_outcome')choices=['确认在界内','确认出界','确认下水'];
 if(model.finished)choices=['分析总结本场','下一场','撤销上次操作'];
 return {model,context,text:context.quiet?'':text,flags,choices,carry:bag(model.profile),strategy:strategy??null};
}
