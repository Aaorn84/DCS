/** Orchestrates system policy -> personal ranking -> course-specific plan. */
import {bag,fairwayFinder} from './bag.ts';
import {surfaces,frame,validPoint,distance,contains,classifyLocation,type Surface} from './geometry.ts';
import {CORE_VERSION} from './protocol.ts';
import {CoreRuleError,type Point} from './roundEngine.ts';
import {courseCandidates as candidates,type Candidate} from './courseAnalysis.ts';
import {rankCandidates,chooseTee,resolveStrategyPolicy} from './strategyPolicy.ts';
import {personalStrategy} from './personalStrategy.ts';
export type PlanIntent={kind?:'default'|'conservative'|'layup'|'alternative'|'aggressive';exclude_club?:string};
const YARD=.9144;
const names:Record<string,string>={water:'水域',ob:'白桩界外区',bunker:'沙坑'};
const round=(n:number)=>Math.round(n);
function description(row:Candidate,unit:string,origin:Point,green:Point){
 const scale=unit==='米'?YARD:1,f=frame(origin),a=f.xy(row.aim_point),g=f.xy(green);let delta=(Math.atan2(a.x,a.y)-Math.atan2(g.x,g.y))*180/Math.PI;delta=(delta+540)%360-180;
 const aim=row.aim_label&&unit==='码'?row.aim_label:`果岭参考方向${Math.abs(delta)<1?'正前方':`${delta<0?'向左':'向右'}约${round(Math.abs(delta))}度`}的${row.target_surface==='green'?'果岭内落点':'球道'}`;
 let text=row.purpose_only?`${row.club}做沙坑短打，目标Carry约${round(row.carry_yards*scale)}${unit}，瞄${aim}。这不是已记录的常态杆距，需确认你能用熟悉的挥幅打出。`:`${row.club}Carry约${round(row.carry_yards*scale)}${unit}，瞄${aim}，预计落区横向约${round(row.width_yards*scale)}${unit}。`;
 if(row.estimated)text+='这支杆的Carry按7号铁杆距暂估，实际执行前按你的杆距确认。';
 if(row.roll_yards)text+=`需落地后再滚约${round(row.roll_yards*scale)}${unit}，现场确认入口通畅且能滚再采用。`;
 if(row.crossings.length){const far=Math.max(...row.crossings.map(c=>c.far_m))/YARD;text+=`沿线有已标障碍，远沿约${round(far*scale)}${unit}；请现场确认飞越余量。`;}
 if(row.nearby.length)text+='落点附近有'+row.nearby.map(k=>names[k]).join('、')+'，给偏差留余量。';
 return text;
}
function pinReference(model:any,hole:any,all:Surface[],origin:Point,center:Point){
 const pin=model.pins?.[String(hole.number)];if(!pin)return center;const green=all.find(s=>s.kind==='green'&&contains(s,center));if(!green)return center;
 const f=frame(center),direction=frame(origin).xy(center),length=Math.hypot(direction.x,direction.y)||1,ux=direction.x/length,uy=direction.y/length;
 const coords=green.rings[0].map(v=>f.xy({longitude:v[0],latitude:v[1],accuracy_m:0}));const depths=coords.map(v=>v.x*ux+v.y*uy),sides=coords.map(v=>v.x*uy-v.y*ux);
 const depth=pin.depth==='front'?Math.min(...depths)*.45:pin.depth==='back'?Math.max(...depths)*.45:0,side=pin.side==='left'?Math.min(...sides)*.35:pin.side==='right'?Math.max(...sides)*.35:0;
 const target=f.point({x:ux*depth+uy*side,y:uy*depth-ux*side});return contains(green,target)?target:center;
}
export function planStrategy(pack:any,model:any,intent:PlanIntent={}){
 if(pack.core_version!==CORE_VERSION||model.core_version!==CORE_VERSION||pack.round?.id!==model.round_id)throw new CoreRuleError('shared strategy scope or version mismatch');
 const personal=personalStrategy(model.profile??pack.profile??{},pack.dispersion);
 const policy=resolveStrategyPolicy(personal,intent.kind);
 const best=(rows:Candidate[],progress=true)=>rankCandidates(rows,policy,personal,progress);
 const base={policy_version:1,personal_strategy:personal,core_version:CORE_VERSION,options:[] as Candidate[],question:null as string|null,two_on_evaluated:false};
 const reply=(text:string,extra:any={})=>({...base,text,...extra});
 if(model.finished)return reply('本场已结束，可以查看成绩或同步记录。');
 if(model.pending)return reply('先确认原球结果并完成罚杆或救济处理，再讨论下一杆。');
 if(model.draft)return reply('先确认或更正当前成绩，再讨论下一杆。');
 if(model.stage!=='playing')return reply('请先开始本场球局。');
 const hole=pack.course?.holes?.find((h:any)=>h.number===model.hole),origin=model.position;
 if(!hole||!validPoint(origin))return reply('请更新到实际球位后再给方案；没有可靠坐标时不猜距离。',{question:'position'});
 if((origin.accuracy_m??0)>25)return reply('当前定位误差较大，请在球旁更新定位，再核对距离与障碍。',{question:'position'});
 const green=hole.objects?.find((o:any)=>o.kind==='green_center');if(!validPoint(green))return reply('本洞果岭参考点缺失，请先核对地图。');
 if(pack.course.crs&&pack.course.crs!=='WGS84')return reply('地图坐标系尚未确认，不能计算落点。');
 const all=surfaces(hole,pack.course.reference_simulation===true),profile=model.profile??pack.profile??{},clubs=bag(profile),unit=profile.units?.value==='米'?'米':'码',scale=unit==='米'?YARD:1;
 if(model.holes?.[String(model.hole)]?.score)return reply('本洞成绩已确认，可以切换下一洞。');
 const rows=model.holes?.[String(model.hole)]?.rows??[],last=[...rows].reverse().find((r:any)=>r.kind==='stroke'&&r.active),lie=model.lie??last?.lie??'unknown';
 const atTee=!rows.some((r:any)=>r.kind==='stroke'&&r.active)&&hole.tee_bbox&&origin.longitude>=hole.tee_bbox[0]&&origin.latitude>=hole.tee_bbox[1]&&origin.longitude<=hole.tee_bbox[2]&&origin.latitude<=hole.tee_bbox[3];
 const positionSurface=classifyLocation(hole,pack.course.reference_simulation===true,all,origin);
 if(['ob','water'].includes(positionSurface)&&last){
  const confirmation=last.boundary_confirmation;
  const confirmedHere=confirmation?.result==='in_bounds'&&validPoint(confirmation.position)&&distance(confirmation.position,origin)<=Math.max(3,origin.accuracy_m??0);
  if(!confirmedHere){
   const alreadyResolved=model.holes[String(model.hole)].incidents?.some((i:any)=>i.stroke_id===last.id);
   if(alreadyResolved)return reply('当前位置仍在地图已标的障碍或界外区域，请核对处理后的实际球位；不会重复加罚杆。',{question:'position'});
   return reply('地图位置提示可能'+(positionSurface==='ob'?'出界':'下水')+'，请按现场边界确认原球结果。',{question:'ball_outcome',suspected:positionSurface==='ob'?'possible_ob':'possible_water'});
  }
 }
 if(!atTee&&lie==='unknown')return reply('现场是球道、长草、沙坑、果岭环，还是果岭上？',{question:'lie'});
 if(lie==='green')return reply('球已在果岭上。结合距离、坡度和速度判断推杆；当前地图不能替你判断果岭坡线。');
 const note=pack.course.reference_simulation===true?'地图为来源坐标演示，现场边界和障碍以球场标示为准。':'现场确认风、球位和地图未覆盖的障碍。';
 if(lie==='rough'&&model.clean_contact==null)return reply('长草里球是浮着、能干净触球，还是埋得较深？',{question:'contact'});
 if(lie==='rough'&&model.clean_contact===false){const short=clubs.find(c=>c.label==='P杆')??clubs.find(c=>/度杆$/.test(c.label));return reply('深草先脱困，'+(short?'可考虑'+short.label+'用你熟悉的小挥幅，':'用你熟悉的短铁小挥幅，')+'先回到看得见的宽处；球道Carry不能直接用于判断这次深草能否飞越障碍。'+note);}
 const target=pinReference(model,hole,all,origin,green),remaining=distance(origin,target)/YARD,seven=clubs.find(c=>c.label==='7号铁');
 function recommend(row:Candidate,label=''){return label+description(row,unit,origin,green);}
 function layup(){
  const available=clubs.filter(c=>!c.driver&&(lie!=='bunker'||c.role==='沙坑'));
  const options=candidates(pack,model,hole,all,available,'fairway',origin,green).filter(r=>r.progress>5&&r.remaining_yards>5);
  const irons=options.filter(r=>!/号木$/.test(r.club));const mids=irons.filter(r=>/^[5-7]号铁$/.test(r.club)||/度杆|P杆/.test(r.club));
  const nonwood=best(irons);const mid=best(mids);
  if(mid&&(!nonwood||mid.progress>=nonwood.progress*.8)&&mid.penalty_samples===0)return mid;
  if(nonwood&&nonwood.penalty_samples===0)return nonwood;
  return best(options.filter(r=>!/号木$/.test(r.club)||r.penalty_samples===0&&r.bunker_samples===0&&r.rough_samples===0&&r.width_yards>=Math.max(40,r.carry_yards*.22)));
 }
 if(atTee&&hole.par>=4){
  const teeOptions=candidates(pack,model,hole,all,clubs.filter(c=>c.high<remaining+10),'fairway',origin,green).filter(r=>r.progress>10),driver=best(teeOptions.filter(r=>r.club==='一号木'));
  const finder=fairwayFinder(profile);let selected:Candidate|undefined;
  if((intent.kind==='conservative'||intent.kind==='alternative')&&finder&&!clubs.some(c=>c.label===finder))return reply('你设置的保底开球杆是'+finder+'，稳定Carry大概多少？可以直接报杆名和码数。',{question:'finder_carry',missing_club:finder});
  if(intent.kind==='conservative'||intent.kind==='alternative'){
   const others=teeOptions.filter(r=>r.club!==(intent.exclude_club??driver?.club));
   const safer=others.filter(r=>!driver||r.risk<driver.risk||r.penalty_samples<=driver.penalty_samples&&r.bunker_samples<=driver.bunker_samples&&r.width_yards>driver.width_yards+3);
   selected=best(safer.filter(r=>r.club===finder))??best(safer);
   if(!selected)return reply('按现有地图和杆距，暂未核对到风险更低且能正常推进的另一落区；请补充保底开球杆或核对现场可用区域。');
  }else selected=chooseTee(teeOptions,policy,personal);
  if(!selected)return reply('暂未核对到可用开球落区，请补充球杆Carry或现场可用落区。',{question:clubs.length?'landing':'carry'});
  let text=recommend(selected)+`按Carry落点估算，下一杆到果岭参考点直线约${round(selected.remaining_yards*scale)}${unit}；尚未计入滚动，不是旗杆距离。`;
  if(selected.club===finder&&intent.kind!=='default')text+='这是你设置的保底开球杆。';
  if(hole.par===5){
   const fairway=clubs.filter(c=>!c.driver),longKnown=fairway.some(c=>!c.estimated&&(c.wood||/铁木杆|^[34]号铁$/.test(c.label)));
   if(!longKnown&&!profile.fairway_carry_status)return reply('你有3号木、5号木或铁木杆吗？各自稳定Carry多少？已有暂估的长铁无需重复报，没有可以说跳过。',{question:'fairway_carry'});
   const longest=fairway.length?Math.max(...fairway.map(c=>c.high)):0,published=hole.published_yardage;
   const budget=selected.carry_yards+longest;
   // Prune BEFORE any second-shot green geometry search; published dogleg length is not straight distance.
   if(typeof published==='number'&&budget<published-10){text+=`按当前已知杆距，两杆Carry合计最多${round(budget*scale)}${unit}，即使考虑约10码滚动也不足公布洞长，先按三杆上果岭安排。`;
    return reply(text+note,{options:[selected],two_on_evaluated:false,two_on_excluded_reason:'distance_budget'});
   }
   const next={...model,position:selected.landing_point,lie:'fairway'},greenOptions=candidates(pack,next,hole,all,fairway,'green',selected.landing_point,green,true),attack=best(greenOptions,false);
   if(attack){text+=`两上候选：开球落定后，第二杆可比较${attack.club}，Carry约${round(attack.carry_yards*scale)}${unit}。`;if(attack.roll_yards)text+=`需再滚约${round(attack.roll_yards*scale)}${unit}，入口必须通畅。`;if(attack.penalty_samples||attack.nearby.some(k=>['ob','water'].includes(k))||attack.width_yards<20)text+='果岭落区或周边罚杆区会限制容错，也可选择分三杆上果岭。';}
   else text+='预计第二杆尚未核对到可用攻果岭落点，先按三杆上果岭安排。';
   return reply(text+note,{options:[selected],two_on_evaluated:true,approach:attack??null});
  }
  return reply(text+note,{options:[selected]});
 }
 if(!model.pins?.[String(model.hole)])return reply('旗在果岭哪里？可以说“左前”“中部”“右后”，不清楚可以跳过。',{question:'pin'});
 const attackClubs=clubs.filter(c=>!c.driver&&(lie!=='bunker'||c.role==='沙坑'));
 const direct=best(candidates(pack,model,hole,all,attackClubs,'green',origin,target,true),false),transition=layup();
 const prefix=`到${model.pins[String(model.hole)].depth==='unknown'?'果岭参考点':'旗位区域估算点'}约${round(remaining*scale)}${unit}。`;
 if(intent.kind==='layup'||intent.kind==='conservative')return transition?reply(prefix+recommend(transition)+`预计下一杆到果岭参考点约${round(transition.remaining_yards*scale)}${unit}。`+note,{options:[transition]}):reply(prefix+'暂未核对到可用过渡落区，请先确认看得见、能正常击球的脱困方向。'+note);
 if(!direct)return transition?reply(prefix+recommend(transition)+`先过渡，预计下一杆到果岭参考点约${round(transition.remaining_yards*scale)}${unit}。`+note,{options:[transition]}):reply(prefix+'已知球杆未覆盖已核对的攻果岭或过渡落点，请补充Carry或现场可用落区。'+note,{question:'carry'});
 let text=prefix+recommend(direct);
 if(lie==='bunker')text+='按沙坑用途选杆，控制到上述短打距离，不套用全挥杆Carry。';
 if(transition&&remaining>(seven?.high??160)&&(direct.penalty_samples>0||direct.width_yards<20)){text+='也可先过渡：'+recommend(transition)+`下一杆到果岭参考点约${round(transition.remaining_yards*scale)}${unit}。`;return reply(text+note,{options:[direct,transition]});}
 return reply(text+note,{options:[direct]});
}
