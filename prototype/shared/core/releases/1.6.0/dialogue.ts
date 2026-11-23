import {parseStrategyPreference} from './personalStrategy.ts';
import {normalizeClub} from './bag.ts';
/** Small offline command grammar. Unknown speech does not become a golf fact. */
export type Turn={commands:{command:string;data:Record<string,any>}[];text:string};
const number=(s:string)=>/^\d+$/.test(s)?Number(s):(({'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10} as Record<string,number>)[s]??NaN);
export const readGolfNumber=number;
const n='(\\d{1,2}|[零一二两三四五六七八九十])';
function club(s:string){s=s.replace(/^一号木$/,'1号木').replace(/^三号木$/,'3号木').replace(/^五号木$/,'5号木');return s==='1号木'?'一号木':s;}
export function localChoices(s:any):string[]{
 if(s.finished)return ['撤销上次操作'];
 if(s.stage==='ready')return ['开始球局'];
 if(s.stage==='finish_confirm')return ['确认结束','撤销上次操作'];
 if(s.draft)return ['确认记录','撤销上次操作'];
 const p=s.pending;
 if(p?.phase==='uncertain')return ['确认在界内','确认出界','确认下水','已找满三分钟仍未找到','已宣告并打暂定球','撤销上次操作'];
 if(p?.phase==='water_method')return p.color?['原位打原球','回上一杆位置重打','向后延线抛球',...(p.color==='red'?['侧向抛球']:[]),'撤销上次操作']:['红桩','黄桩','原位打原球'];
 if(p?.phase==='provisional_position')return [...(p.position_candidate?['已到暂定球位置']:[]),'已到暂定球位置，坐标暂未知','撤销上次操作'];
 if(p?.method==='stroke_distance')return ['已回上一杆位置，坐标暂未知','撤销上次操作'];
 if(p)return [...(p.position_candidate&&p.drop_confirmed&&p.ball_stayed&&(!['back_on_line','lateral'].includes(p.method)||p.crossing_confirmed)?['确认在当前位置']:[]),'已确认最后越界点','已在合法位置抛球','球停在救济区内','已确认越界点，合法抛球并停在救济区内，坐标暂未知','撤销上次操作'];
 const h=s.holes[String(s.hole)];if(h.score||h.skipped)return s.hole===18?['结束球局','撤销上次操作']:['下一洞','结束球局','撤销上次操作'];
 return s.selection?['记录已击球','这洞四杆两推','这洞五杆两推','结束球局','撤销上次操作']:['这杆怎么打','有没有保守方案','一号木','5号木','7号铁','P杆','58度杆','推杆','这洞四杆两推','下一洞','这洞先不记','结束球局'];
}
export function parseLocalTurn(s:any,input:string):Turn{
 const clean=input.replace(/[\s，,。！？!?]/g,'').replace(/^(?:看到了|看到球了|球在|落在)/,'').replace(/^在(?=球道|长草|沙坑|果岭)/,'').replace(/^上果岭了$/,'果岭上').replace(/^(沙坑|长草)里$/,'$1');const result=(text:string,commands:Turn['commands']=[])=>({text,commands});const one=(command:string,data:Record<string,any>={})=>[{command,data}];
 if(clean==='撤销上次操作'||clean==='撤销上一条')return result('已撤销上次操作。',one('undo'));
 if(s.finished)return result('本场已经结束，可以联网同步本机记录。');
 if(s.stage==='ready')return clean==='开始球局'?result('已在本机开始球局。',one('start')):result('离线资料已准备，可以说“开始球局”。');
 if(s.stage==='finish_confirm')return /^(确认|确认结束)$/.test(clean)?result('本场已在本机收好，联网后可同步。',one('confirm_finish',{confirmed:true})):result('确认结束这场球吗？');
 if(s.draft&&/^(确认|确认记录)$/.test(clean))return result('成绩已在本机保存。',one('confirm_score',{confirmed:true}));
 const preference=parseStrategyPreference(input);
 if(preference&&!s.pending&&!s.draft)return result('已记下你的长期策略偏好；仍会核对这杆的障碍和落区。',one('set_strategy_preference',{preference}));
 const p=s.pending;
 if(!p&&!s.draft&&/^(确认出界|确认OB|确认下水)$/i.test(clean)){
  const h=s.holes[String(s.hole)],last=[...h.rows].reverse().find((r:any)=>r.kind==='stroke'&&r.active);
  if(last){
   if(h.incidents.some((i:any)=>i.stroke_id===last.id))return result('这杆的结果已登记；不会重复加罚杆。');
   const water=clean==='确认下水';return result(water?'已确认或几乎确定球停在罚杆区。现场是红桩还是黄桩？':'已确认出界，罚一杆并回上一杆位置重打。',[...one('report_incident',{cause:water?'possible_water':'possible_ob'}),...one('resolve_ball',{result:water?'water':'ob',...(water?{known_or_virtually_certain:true}:{})})]);
  }
 }
 if(p?.phase==='uncertain'){
  if(/^(确认在界内|原球在界内|找到了原球)$/.test(clean))return result('原球在界内；暂定球如已打，不计入成绩。',one('resolve_ball',{result:'in_bounds'}));
  if(/^(确认出界|确认OB)$/i.test(clean))return result('已确认出界，罚一杆；有暂定球时转为使用中球，否则回上一杆位置重打。',one('resolve_ball',{result:'ob'}));
  if(clean==='确认下水')return result('确认球在罚杆区。原球可以打时可原位打；采取救济需区分红桩和黄桩。',one('resolve_ball',{result:'water',known_or_virtually_certain:true}));
  if(clean==='已找满三分钟仍未找到')return result('按罚杆区外遗失球处理，罚一杆并加距离。',one('resolve_ball',{result:'lost',search_expired:true}));
  if(clean==='已宣告并打暂定球')return s.selection?result('暂定球先单独登记。',one('play_provisional',{club:s.selection.club,announced:true})):result('请报暂定球实际使用的球杆，例如“暂定球用5号木已宣告并打”。');
  const provisional=clean.match(/^暂定球用(.+)已宣告并打$/);if(provisional)return result('暂定球先单独登记，确认原球结果后再决定是否计入。',one('play_provisional',{club:club(provisional[1]),announced:true}));
  return result('先确认原球在界内、出界、下水，还是找满三分钟仍未找到。');
 }
 if(p?.phase==='water_method'){
  if(clean==='红桩'||clean==='黄桩')return result(clean==='红桩'?'红桩可比较回原位、向后延线或合法侧向救济。':'黄桩可回原位或向后延线救济，不能侧向两杆抛球。',one('set_penalty_area_color',{color:clean==='红桩'?'red':'yellow'}));
  if(clean==='原位打原球')return result('选择原位打原球，不加救济罚杆。',one('choose_relief',{method:'play_original'}));
  const method=clean==='回上一杆位置重打'?'stroke_distance':clean==='向后延线抛球'?'back_on_line':clean==='侧向抛球'?'lateral':null;
  if(method)return result(method==='stroke_distance'?'回上一杆位置，实际完成后确认。':'先确认最后越过罚杆区边界的点；依法抛球，并确认球停在救济区内。',one('choose_relief',{method,color:p.color}));
  return result('请先说明红桩或黄桩，再选择处理方式。');
 }
 if(p){
  if(clean==='已到暂定球位置'&&p.phase==='provisional_position')return p.position_candidate?result('已确认暂定球的位置，移动不算击球。',one('complete_relief',{legal_confirmed:true,point:p.position_candidate})):result('请先更新到暂定球位置，或选择坐标暂未知。');
  if(clean==='已确认最后越界点')return result('已记录最后越界点的确认。',one('attest_relief',{step:'crossing',confirmed:true}));
  if(clean==='已在合法位置抛球')return result('球是否停在救济区内？',one('attest_relief',{step:'drop',confirmed:true}));
  if(clean==='球停在救济区内')return result('已记录，请更新处理后的球位；若已更新，可说“确认在当前位置”。',one('attest_relief',{step:'stayed',confirmed:true}));
  if(/^(确认在当前位置|就在这里完成救济|就在当前位置完成救济)$/.test(clean)){
   if(p.method==='stroke_distance')return result('已确认回上一杆位置，未新增击球。',one('complete_relief',{legal_confirmed:true,returned_to_previous:true,...(p.position_candidate?{point:p.position_candidate}:{position_unknown_confirmed:true})}));
   if(!p.position_candidate)return result('请更新处理后的球位，或选择坐标暂未知。');
   if(p.phase!=='provisional_position'&&(!p.drop_confirmed||!p.ball_stayed||['back_on_line','lateral'].includes(p.method)&&!p.crossing_confirmed))return result('先确认最后越界点、合法抛球和球停在救济区内，再确认当前位置。');
   return result('已确认处理后的球位，抛球和移动不算击球。',one('complete_relief',{legal_confirmed:true,point:p.position_candidate,crossing_confirmed:p.crossing_confirmed===true,ball_stayed:p.ball_stayed===true}));
  }
  if(p.method==='stroke_distance'&&/^(已回原位|已回上一杆位置|已回发球台|已经回原位)$/.test(clean))return result('已确认回上一杆位置，未新增击球。',one('complete_relief',{legal_confirmed:true,returned_to_previous:true,position_unknown_confirmed:true}));
  if(clean==='已到暂定球位置坐标暂未知')return result('已记录暂定球成为使用中球后的球位待定位，移动不算击球。',one('complete_relief',{legal_confirmed:true,position_unknown_confirmed:true}));
  if(clean==='已回上一杆位置坐标暂未知')return result('已确认回原位；有原起点坐标时沿用原起点，移动不算击球。',one('complete_relief',{legal_confirmed:true,returned_to_previous:true,position_unknown_confirmed:true}));
  if(clean==='已确认越界点合法抛球并停在救济区内坐标暂未知')return result('已按你的确认登记救济和罚杆，球位坐标暂未知；抛球不算击球。',one('complete_relief',{legal_confirmed:true,crossing_confirmed:true,ball_stayed:true,position_unknown_confirmed:true}));
  return result('请先确认处理已完成；未更新坐标时可以选择标有“坐标暂未知”的确认项。');
 }
 if(clean==='跳过球道杆距'||clean==='没有球道木和铁木杆')return result('先按现有杆距安排。',one('set_fairway_carry_status',{status:clean==='跳过球道杆距'?'unknown':'none'}));
 const purpose=clean.match(/^([4-6]\d)(?:度杆)?(?:用于|打)?沙坑(?:用)?$/);if(purpose)return result('已记录'+purpose[1]+'度杆用于沙坑，未猜测Carry。',one('set_club_purpose',{club:purpose[1]+'度杆',use:'沙坑'}));
 const bareWedge=clean.match(/^(4[6-9]|5[0-9]|6[0-4])(?:吧)?$/);if(bareWedge)return result('已选'+bareWedge[1]+'度杆，实际打完再记录。',one('select_club',{club:bareWedge[1]+'度杆'}));
 const coordinate=input.trim().match(/^(?:球位|位置)\s*(-?\d+(?:\.\d+)?)\s*[,， ]\s*(-?\d+(?:\.\d+)?)(?:\s*[,， ]\s*(\d+(?:\.\d+)?))?$/);
 if(coordinate)return result('已按你提供的坐标更新球位，未生成击球。',one('set_position',{point:{latitude:Number(coordinate[1]),longitude:Number(coordinate[2]),accuracy_m:Number(coordinate[3]??0)}}));
 const carryPattern=/(一号木|1号木|三号木|五号木|[3-9]号木|(?:[2-9]号)?铁木杆|[2-9]号铁|P杆|[4-6]\d度杆)\s*(\d{1,3})(?:\s*(?:到|[-–~])\s*(\d{1,3}))?\s*(码|米)?/g;
 const carries=[...input.matchAll(carryPattern)];
 const remainder=input.replace(carryPattern,'').replace(/[\s，,、；;。]/g,'');
 if(carries.length&&!remainder)return result('已记录球杆Carry。',carries.map(m=>({command:'set_club_carry',data:{club:normalizeClub(club(m[1])),low:Number(m[2])/(m[4]==='米'?.9144:1),high:Number(m[3]??m[2])/(m[4]==='米'?.9144:1)}})));
 const finder=clean.match(/^(?:保底球杆|保底开球杆)(?:设置为|设为|用|是)?(.+)$/);
 if(finder){
  const values=[...finder[1].matchAll(carryPattern)];
  if(values.length===1&&finder[1].replace(carryPattern,'')===''){const m=values[0],label=normalizeClub(club(m[1])),scale=m[4]==='米'?1/.9144:1;return result('已记录保底开球杆和Carry。',[...one('set_club_carry',{club:label,low:Number(m[2])*scale,high:Number(m[3]??m[2])*scale}),...one('set_fairway_finder',{club:label})]);}
  return result('已设置保底开球杆，之后保守方案会结合比较。',one('set_fairway_finder',{club:normalizeClub(club(finder[1]))}));
 }
 if(/^(?:浅草|球浮着|能干净触球|浅草能干净触球)$/.test(clean))return result('已确认浅草、能干净触球。',one('set_lie',{lie:'rough',clean_contact:true}));
 if(/^(?:埋得较深|深草|球埋着)$/.test(clean))return result('已确认深草，优先考虑脱困。',one('set_lie',{lie:'rough',clean_contact:false}));
 const pins:Record<string,[string,string]>={'左前':['front','left'],'右前':['front','right'],'左后':['back','left'],'右后':['back','right'],'左中':['middle','left'],'右中':['middle','right'],'前部':['front','center'],'中部':['middle','center'],'后部':['back','center'],'前旗':['front','center'],'中旗':['middle','center'],'后旗':['back','center'],'旗位不清楚':['unknown','unknown'],'跳过旗位':['unknown','unknown']};
 const flagText=clean.replace(/^(前|中|后)旗偏(左|右)$/,(_,depth,side)=>side+depth);const pin=pins[flagText];if(pin)return result('已记录本洞旗位区域。',one('set_pin',{depth:pin[0],side:pin[1]}));
 const explicitHole=clean.match(/^(更正)?第(\d{1,2})洞(.+)$/);
 if(explicitHole){const target=Number(explicitHole[2]);if(!s.holes[String(target)])return result('请报1到18洞的成绩。');const parsed=parseLocalTurn({...s,hole:target},(explicitHole[1]??'')+explicitHole[3]);if(parsed.commands.some(c=>c.command==='draft_score')){for(const cmd of parsed.commands)if(cmd.command==='draft_score')cmd.data.hole=target;return parsed;}}
 const selected=clean.match(/^(?:好|好的)?(?:用|选)?(一号木|1号木|[3-9三五]号木|(?:[2-9]号)?铁木杆|[2-9]号铁|P杆|推杆|[4-6]\d度杆)(?:吧)?$/);
 if(selected)return result('已选'+club(selected[1])+'，实际打完再说“记录已击球”。',one('select_club',{club:club(selected[1])}));
 if(/^(记录已击球|这杆打完了|已经打了)$/.test(clean))return result('已在本机记录这一杆；可以补充球道、长草、沙坑或果岭上的落点。',one('record_stroke'));
 const lies:Record<string,string>={'球道':'fairway','球道中间':'fairway','长草':'rough','沙坑':'bunker','果岭环':'fringe','果岭上':'green','果岭边':'unknown','果岭边长草':'rough','果岭边沙坑':'bunker','果岭附近长草':'rough','球道左侧':'fairway','球道右侧':'fairway'};
 if(clean in lies)return result('已补充这杆落点，不新增击球。',one(s.holes[String(s.hole)].rows.some((r:any)=>r.kind==='stroke'&&r.active)?'set_landing':'set_lie',{lie:lies[clean],area:/果岭边|果岭附近/.test(clean)?'greenside':clean==='球道左侧'?'fairway_left':clean==='球道右侧'?'fairway_right':null}));
 if(/^(可能出界|好像OB了|可能OB了|出界了|下水了|可能下水|可能找不到)$/i.test(clean))return result('已记录待确认情况。请确认原球结果；只有可能出界或在罚杆区外遗失时才考虑暂定球。',one('report_incident',{cause:/水/.test(clean)?'possible_water':/找不到/.test(clean)?'possible_lost':'possible_ob'}));
 const score=clean.match(new RegExp('^(?:更正)?(?:这洞|本洞)?'+n+'杆'+n+'推(?:'+n+'(?:罚杆|罚))?$'));
 if(score){const h=s.holes[String(s.hole)];const penalties=h.rows.filter((r:any)=>r.kind==='penalty'&&r.active).reduce((v:number,r:any)=>v+r.amount,0);const total=number(score[1]),putts=number(score[2]);return result('第'+s.hole+'洞'+total+'杆、'+putts+'推，罚杆'+(score[3]?number(score[3]):penalties)+'。确认记录吗？',one('draft_score',{total,putts,penalties:score[3]?number(score[3]):penalties,correct_existing:clean.startsWith('更正')}));}
 if(clean==='这洞先不记'||clean==='跳过本洞记分')return result('这洞成绩留空，不算零杆。',[...one('skip_score',{confirmed:true}),...one(s.hole===18?'request_finish':'switch_hole',s.hole===18?{}:{hole:s.hole+1})]);
 const switchTo=clean.match(/^切换到第(\d{1,2})洞$/);if(switchTo)return result('已切换到第'+switchTo[1]+'洞。',one('switch_hole',{hole:Number(switchTo[1])}));
 if(clean==='下一洞')return result(s.hole===18?'确认结束本场球吗？':'已切到第'+(s.hole+1)+'洞。',one(s.hole===18?'request_finish':'switch_hole',s.hole===18?{}:{hole:s.hole+1}));
 if(clean==='结束球局')return result('确认结束本场球吗？未确认的球洞会保留为空。',one('request_finish'));
 return result('这句话尚未记为击球或成绩。离线记分可使用下方选项，或说“这洞六杆两推”；可以直接问“这杆怎么打”。');
}
export function localRuleError(message:string):string{
 if(message.startsWith('本机'))return message;
 const messages:Record<string,string>={'explicit score correction required':'这洞已确认成绩；需要修改时可说“更正这洞六杆两推”。','club required':'请先说明这杆实际使用的球杆。','resolve ball first':'请先处理原球及救济，再进行下一杆。','score below recorded strokes':'总杆少于已记录的击球、罚杆和推杆合计，请核对。','reported penalties disagree with ledger':'报告的罚杆与已处理的事故记录不一致，请先核对。','score or explicitly skip current hole first':'这洞还没有确认成绩，请先报成绩。','yellow has no lateral relief':'黄桩不能侧向两杆救济，请改选回原位或向后延线。','confirm or correct draft first':'先确认或更正待确认成绩。','hole already scored':'本洞已经确认成绩，需要更正时先撤销上次操作。','provisional not permitted for water-only risk':'仅可能进入罚杆区时不能按此流程打暂定球。','nothing to undo':'没有可撤销的本地操作。','penalty area color required':'请先说明红桩还是黄桩。','stroke required':'还没有对应的实际击球，请先确认已打这一杆。'};
 return messages[message]??'这次操作未保存。请核对当前球局状态，或使用下方可用选项。';
}
