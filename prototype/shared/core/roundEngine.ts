import {stampProfileChanges} from './profileMemory.ts';
import {appendStrategyUsage} from './personalStrategy.ts';
import {CORE_VERSION} from './protocol.ts';
import {normalizeClub} from './bag.ts';
/** Versioned deterministic rules core. No GPS swing inference, Carry calibration, or penalty probability. */
export type Point={latitude:number;longitude:number;accuracy_m:number;elevation?:import('./elevation.ts').Elevation};
export type LocalCommand={v:1;semantics:2;id:string;at:string;expected_revision:number;command:string;data?:Record<string,any>};
export type LocalRound=any;
const clone=<T>(v:T):T=>JSON.parse(JSON.stringify(v));
export class CoreRuleError extends Error {}
function fail(message:string):never{throw new CoreRuleError(message);}
function check(value:any,message:string):asserts value {if(!value)fail(message);}
function integer(v:any,min:number,max:number){check(Number.isInteger(v)&&v>=min&&v<=max,'invalid integer');return v;}
function point(p:any):Point{check(p&&typeof p==='object','position required');for(const [k,lo,hi] of [['latitude',-90,90],['longitude',-180,180],['accuracy_m',0,10000]] as const)check(typeof p[k]==='number'&&Number.isFinite(p[k])&&p[k]>=lo&&p[k]<=hi,'invalid position');return clone(p);}
function canonical(v:any):string{if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(v&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';return JSON.stringify(v);}
const CONTEXT=['hole','stage','position','selection','pending','draft','finished','lie','clean_contact','pins','profile'];
export function createLocalRound(pack:any):LocalRound{
 check(pack?.core_version===CORE_VERSION,'shared core version mismatch');
 check(pack?.schema===1&&pack.round?.id&&pack.round?.tee,'incompatible offline package');
 check(Array.isArray(pack.course?.holes)&&pack.course.holes.length===18,'18 holes required');
 const holes:any={};for(const h of pack.course.holes){integer(h.number,1,18);integer(h.par,2,7);check(!holes[String(h.number)],'duplicate hole');holes[String(h.number)]={par:h.par,rows:[],incidents:[],score:null,skipped:false};}
 const hole=integer(pack.round.start_hole??1,1,18);
 return {schema:1,core_version:CORE_VERSION,profile:clone(pack.profile??{}),pins:{},lie:null,clean_contact:null,round_id:pack.round.id,course_id:pack.course.course_id,tee:pack.round.tee,hole,stage:'ready',position:null,selection:null,pending:null,draft:null,finished:false,holes,revision:0,receipts:{},undo:[]};
}
function counts(h:any){return {physical:h.rows.filter((r:any)=>r.kind==='stroke'&&r.active).length,putts:h.rows.filter((r:any)=>r.kind==='stroke'&&r.active&&r.is_putt===true).length,ambiguous_putts:h.rows.filter((r:any)=>r.kind==='stroke'&&r.active&&r.club==='推杆'&&r.is_putt==null).length,penalties:h.rows.filter((r:any)=>r.kind==='penalty'&&r.active).reduce((n:number,r:any)=>n+r.amount,0)};}
export function localTotals(s:LocalRound){const scores=Object.values(s.holes).map((h:any)=>h.score).filter(Boolean) as any[];return {holes:scores.length,total:scores.reduce((n,h)=>n+h.total,0),putts:scores.reduce((n,h)=>n+h.putts,0),penalties:scores.reduce((n,h)=>n+h.penalties,0)};}
function last(h:any){return [...h.rows].reverse().find((r:any)=>r.kind==='stroke'&&r.active);}
export function applyLocalCommand(original:LocalRound,event:LocalCommand):LocalRound{
 check(original.core_version===CORE_VERSION,'shared core version mismatch');
 check(event?.semantics===2,'unsupported command semantics');
 check(event?.v===1&&/^[A-Za-z0-9_-]{1,100}$/.test(event.id),'invalid local command');
 check(typeof event.at==='string'&&/(Z|[+-]\d\d:\d\d)$/.test(event.at)&&Number.isFinite(Date.parse(event.at)),'invalid local time');
 const prior=original.receipts[event.id];if(prior){check(canonical(prior)===canonical(event),'event id reused');return original;}
 check(original.revision===event.expected_revision,'local revision conflict');check(Object.keys(original.receipts).length<3000,'local round event limit');
 const s=clone(original),d=clone(event.data??{}),command=event.command;
 const targetNumber=command==='draft_score'?(d.hole??s.hole):command==='confirm_score'?(s.draft?.hole??s.hole):s.hole;integer(targetNumber,1,18);const h=s.holes[String(targetNumber)];
 const before:any={hole_number:targetNumber,hole:clone(h),context:{}};for(const k of CONTEXT)before.context[k]=clone(s[k]);
 function penalty(cause:string,shotId:string){if(h.rows.some((r:any)=>r.kind==='penalty'&&r.stroke_id===shotId))return;const index=h.rows.findIndex((r:any)=>r.id===shotId);h.rows.splice(index+1,0,{id:event.id+'-penalty',kind:'penalty',active:true,amount:1,cause,stroke_id:shotId});}
 function selection(club:any){check(typeof club==='string'&&club.trim().length>0&&club.length<=30,'club required');return club;}
 const allowed=['set_strategy_preference','attest_relief','set_club_purpose','set_fairway_carry_status','set_lie','set_pin','set_club_carry','set_fairway_finder','start','set_position','select_club','record_stroke','set_landing','report_incident','play_provisional','resolve_ball','set_penalty_area_color','choose_relief','complete_relief','draft_score','confirm_score','skip_score','navigate_hole','switch_hole','request_finish','confirm_finish','undo'];
 check(allowed.includes(command),'unsupported local command');
 if(command==='undo'){
  check(s.undo.length,'nothing to undo');const entry=s.undo.pop();s.holes[String(entry.hole_number)]=entry.hole;for(const k of CONTEXT)s[k]=entry.context[k];
 }else{
  check(!s.finished,'round already finished');
  if(s.stage==='ready')check(['start','set_position'].includes(command),'start round first');
  if(s.stage==='finish_confirm')check(command==='confirm_finish','finish confirmation pending');
  if(s.pending)check(['attest_relief','set_position','set_landing','play_provisional','resolve_ball','set_penalty_area_color','choose_relief','complete_relief'].includes(command),'resolve ball first');
  if(s.draft)check(['draft_score','confirm_score'].includes(command),'confirm or correct draft first');
  if(command==='start'){check(s.stage==='ready','round already started');s.stage='playing';}
  else if(command==='set_strategy_preference'){check(['balanced','distance','control'].includes(d.preference),'invalid strategy preference');s.profile.strategy_preference={value:d.preference,source:'user_report'};}
  else if(command==='set_club_purpose'){const club=selection(d.club),match=club.match(/^([4-6]\d)度杆$/);check(match&&d.use==='沙坑','invalid club purpose');s.profile.lofted_wedge_uses={value:{...(s.profile.lofted_wedge_uses?.value??{}),[match[1]]:'沙坑'},source:'user_report'};}
  else if(command==='set_fairway_carry_status'){check(['none','unknown'].includes(d.status),'invalid fairway carry status');s.profile.fairway_carry_status=d.status;}
  else if(command==='set_lie'){check(['tee','fairway','rough','bunker','fringe','green','unknown'].includes(d.lie),'invalid lie');check(d.clean_contact==null||typeof d.clean_contact==='boolean','invalid contact');s.lie=d.lie;s.clean_contact=d.clean_contact??null;}
  else if(command==='set_pin'){check(['front','middle','back','unknown'].includes(d.depth),'invalid pin depth');check(['left','center','right','unknown'].includes(d.side),'invalid pin side');s.pins[String(s.hole)]={depth:d.depth,side:d.side};}
  else if(command==='set_club_carry'){const club=normalizeClub(selection(d.club));check(/^(一号木|[3-9]号木|(?:[2-9]号)?铁木杆|[2-9]号铁|P杆|[4-6]\d度杆)$/.test(club),'unsupported carry club');check(Number.isFinite(d.low)&&Number.isFinite(d.high)&&d.low>=0&&d.high>0&&d.low<=d.high&&d.high<=400,'invalid carry range');s.profile.bag_overrides={...(s.profile.bag_overrides??{}),[club]:{low:d.low,high:d.high,source:'user_report'}};const keys:Record<string,string>={'一号木':'driver','3号木':'three_wood','5号木':'five_wood','铁木杆':'hybrid','7号铁':'seven','3号铁':'iron3','4号铁':'iron4','P杆':'pitching_wedge'};if(keys[club]&&d.low===d.high)s.profile[keys[club]]={value:{distance:d.high,units:'码',distance_type:'carry',club_name:club},source:'user_report'};}
  else if(command==='set_fairway_finder'){s.profile.fairway_finder={value:{club:normalizeClub(selection(d.club))},source:'user_report'};}
  else if(command==='set_position'){const next=point(d.point);if(s.pending&&['relief_position','provisional_position'].includes(s.pending.phase))s.pending.position_candidate=clone(next);if(s.selection&&(!s.position||s.position.latitude!==next.latitude||s.position.longitude!==next.longitude))s.selection.target=null;s.position=next;}
  else if(command==='select_club'){check(!h.score,'hole already scored');check(d.strategy_choice==null||['control','distance'].includes(d.strategy_choice),'invalid strategy choice');s.selection={strategy_choice:d.strategy_choice??null,club:selection(d.club),target:d.target?point(d.target):null,origin:clone(s.position),swing_type:d.swing_type??'unknown',event_id:event.id};}
  else if(command==='record_stroke'){
   check(!h.score,'hole already scored');const club=selection(d.club??s.selection?.club);check(h.rows.length<100,'hole record limit');
   check(d.is_putt==null||typeof d.is_putt==='boolean','invalid putting flag');const isPutt=d.is_putt??(s.lie==='green'?true:club==='推杆'&&(!s.lie||s.lie==='unknown')?null:false);
   if(s.selection?.club===club)appendStrategyUsage(s.profile,s.round_id,s.hole,s.selection.strategy_choice);
   h.rows.push({id:event.id,kind:'stroke',active:true,club,is_putt:isPutt,origin:clone(d.origin?point(d.origin):s.position),landing:d.landing?point(d.landing):null,lie:d.lie??'unknown',area:d.area??null,confirmed_target:s.selection?.club===club?clone(s.selection.target):null,source:'user_report'});
   s.position=d.landing?point(d.landing):null;s.lie=d.lie??null;s.clean_contact=null;s.selection=null;
  }else if(command==='set_landing'){
   check(!h.score,'hole already scored');const r=d.stroke_id?h.rows.find((r:any)=>r.id===d.stroke_id&&r.kind==='stroke'):last(h);check(r,'stroke required');
   const current=r===last(h);
   if(d.point){r.landing=point(d.point);if(!s.pending&&current){s.position=point(d.point);if(s.selection)s.selection.target=null;}else if(s.pending?.stroke_id===r.id)s.pending.original_position=point(d.point);}
   if(d.lie){check(['fairway','rough','bunker','fringe','green','unknown'].includes(d.lie),'invalid lie');r.lie=d.lie;r.area=d.area??null;if(current){s.lie=d.lie;s.clean_contact=null;}}
  }else if(command==='report_incident'){
   check(!h.score,'hole already scored');check(!s.pending,'incident already pending');const r=last(h);check(r,'stroke required');
   check(['possible_ob','possible_lost','possible_water','unknown'].includes(d.cause),'confirm outcome separately');
   s.pending={stroke_id:r.id,cause:d.cause,phase:'uncertain',origin:clone(r.origin),original_position:clone(r.landing),provisional_id:null};s.selection=null;
  }else if(command==='play_provisional'){
   check(s.pending&&s.pending.phase==='uncertain'&&['possible_ob','possible_lost','unknown'].includes(s.pending.cause),'provisional not permitted for water-only risk');
   check(!s.pending.provisional_id,'provisional already recorded');check(d.announced===true,'announce provisional before stroke');
   h.rows.push({id:event.id,kind:'stroke',active:false,provisional:true,club:selection(d.club),origin:clone(s.pending.origin),landing:null,lie:'unknown',confirmed_target:null,source:'user_report'});s.pending.provisional_id=event.id;
  }else if(command==='resolve_ball'){
   check(s.pending?.phase==='uncertain','uncertain incident required');const p=s.pending;check(['in_bounds','ob','lost','water'].includes(d.result),'invalid ball result');
   if(d.result==='lost')check(d.search_expired===true,'confirm search time expired');
   if(d.result==='water')check(d.known_or_virtually_certain===true,'water confirmation required');
   if(d.result==='in_bounds'){s.position=clone(p.original_position);const originalRow=h.rows.find((r:any)=>r.id===p.stroke_id);originalRow.boundary_confirmation={result:'in_bounds',position:clone(p.original_position),at:event.at};s.pending=null;}
   else{
    p.cause=d.result;h.incidents.push({id:event.id,stroke_id:p.stroke_id,cause:d.result});
    if(['ob','lost'].includes(d.result)){
     penalty(d.result,p.stroke_id);
     if(p.provisional_id){const r=h.rows.find((r:any)=>r.id===p.provisional_id);r.active=true;r.provisional=false;p.phase='provisional_position';}
     else{p.phase='relief_position';p.method='stroke_distance';}
    }else{p.phase='water_method';}
   }
  }else if(command==='set_penalty_area_color'){
   check(s.pending?.phase==='water_method','water relief required');check(['red','yellow'].includes(d.color),'penalty area color required');s.pending.color=d.color;
  }else if(command==='choose_relief'){
   const p=s.pending;check(p?.phase==='water_method','water relief required');d.color=d.color??p.color;
   check(['play_original','stroke_distance','back_on_line','lateral','drop_zone'].includes(d.method),'unsupported relief');
   if(d.method==='play_original'){s.position=clone(p.original_position);s.pending=null;}
   else{
    check(['red','yellow'].includes(d.color),'penalty area color required');if(d.method==='lateral')check(d.color==='red','yellow has no lateral relief');
    if(d.method==='drop_zone')check(d.authorized_drop_zone===true,'authorized drop zone required');
    p.method=d.method;p.color=d.color;p.phase='relief_position';
   }
  }else if(command==='attest_relief'){
   const p=s.pending;check(p&&['water_method','relief_position'].includes(p.phase),'relief position required');check(d.confirmed===true&&['crossing','drop','stayed'].includes(d.step),'invalid relief attestation');
   if(d.step!=='crossing')check(p.phase==='relief_position'&&p.method!=='stroke_distance','drop relief required');
   if(d.step==='crossing')p.crossing_confirmed=true;else if(d.step==='drop')p.drop_confirmed=true;else p.ball_stayed=true;
  }else if(command==='complete_relief'){
   const p=s.pending;check(p&&['relief_position','provisional_position'].includes(p.phase),'relief position required');check(d.legal_confirmed===true,'confirm legal relief position');
   function reliefPoint(){if(d.point)return point(d.point);check(d.position_unknown_confirmed===true,'position required');return null;}
   if(p.phase==='provisional_position'){s.position=reliefPoint();h.rows.find((r:any)=>r.id===p.provisional_id).landing=clone(s.position);}
   else if(p.method==='stroke_distance'){check(p.origin||d.returned_to_previous===true,'confirm previous position');s.position=p.origin?clone(p.origin):reliefPoint();}
   else{check(d.ball_stayed===true,'confirm ball stayed in relief area');if(['back_on_line','lateral'].includes(p.method))check(d.crossing_confirmed===true,'confirm last crossing point');s.position=reliefPoint();}
   if(p.cause==='water')penalty('water',p.stroke_id);s.pending=null;s.selection=null;s.lie=null;s.clean_contact=null;
  }else if(command==='draft_score'){
   if(h.score){check(d.correct_existing===true,'explicit score correction required');h.rows=h.rows.filter((r:any)=>!['score_placeholder','score_report'].includes(r.source));h.score=null;}const n=counts(h);const total=integer(d.total,1,30),putts=integer(d.putts,0,30);
   check(n.penalties===integer(d.penalties,0,29),'reported penalties disagree with ledger');check(putts>=n.putts,'putts below recorded strokes');
   check(total>=n.physical+n.penalties+Math.max(0,putts-n.putts-n.ambiguous_putts)&&total>=putts+n.penalties,'score below recorded strokes');s.draft={hole:targetNumber,total,putts,penalties:n.penalties};
  }else if(command==='confirm_score'){
   check(s.draft?.hole===targetNumber&&d.confirmed===true,'explicit score confirmation required');const score=clone(s.draft),n=counts(h);
   const missingPutts=Math.max(0,score.putts-n.putts-n.ambiguous_putts);
   const unknown=score.total-score.penalties-n.physical-missingPutts;
   for(let i=0;i<unknown;i++)h.rows.push({id:event.id+'-unknown-'+i,kind:'stroke',active:true,club:null,origin:null,landing:null,lie:'unknown',source:'score_placeholder'});
   for(let i=0;i<missingPutts;i++)h.rows.push({id:event.id+'-putt-'+i,kind:'stroke',active:true,club:'推杆',is_putt:true,origin:null,landing:null,lie:'green',source:'score_report'});
   delete score.hole;h.score=score;s.draft=null;if(targetNumber===s.hole)s.selection=null;
  }else if(command==='skip_score'){check(d.confirmed===true,'explicit skip required');h.skipped=true;}
  else if(command==='navigate_hole'){integer(d.hole,1,18);s.hole=d.hole;s.position=null;s.selection=null;s.lie=null;s.clean_contact=null;}
  else if(command==='switch_hole'){integer(d.hole,1,18);check(h.score||h.skipped,'score or explicitly skip current hole first');check(d.hole!==s.hole,'already on hole');s.hole=d.hole;s.position=null;s.selection=null;s.lie=null;s.clean_contact=null;}
  else if(command==='request_finish'){s.stage='finish_confirm';}
  else if(command==='confirm_finish'){check(s.stage==='finish_confirm'&&d.confirmed===true,'finish confirmation required');s.finished=true;s.stage='finished';}
  if(['set_strategy_preference','set_club_purpose','set_fairway_carry_status','set_club_carry','set_fairway_finder'].includes(command)||command==='record_stroke'&&before.context.selection?.strategy_choice)stampProfileChanges(before.context.profile,s.profile,{at:event.at,round_id:s.round_id,order:original.revision+1});
  s.undo.push(before);if(s.undo.length>20)s.undo.shift();
 }
 s.revision=original.revision+1;s.receipts[event.id]=clone(event);return s;
}
