"""Prospective approach decisions and previous-shot questions; never infer execution."""
import re,copy
from club_selection import selection
from round_state import fact_value

def previous_distance(text):
 return bool(re.search(r'上一杆|上杆|刚才那(?:一)?杆|刚刚那(?:一)?杆',text) and re.search(r'多少|多远|距离|几码|几米',text))

def distance_answer(s,text):
 from shot_chain import node_live
 from round_state import refs_current
 ch=s.get('shot_chain',{});nodes=ch.get('nodes',{});hole=fact_value(s,'context.active_hole')
 shots=[]
 for shot in ch.get('shots',{}).values():
  execution=nodes.get(shot.get('slots',{}).get('execution'))
  if shot.get('hole')==hole and node_live(s,execution):shots.append(shot)
 if shots:
  latest=max(shots,key=lambda row:row['stroke_number'])
  ex=nodes.get(latest.get('slots',{}).get('execution'));gps=nodes.get(latest.get('slots',{}).get('gps'))
  if node_live(s,gps):
   candidates=[s.get('derived',{}).get(key,{}) for key in latest.get('learning_candidates',[])]
   candidates=[v for v in candidates if v.get('valid') and refs_current(s,v.get('deps',{})) and 'chain:'+ex['node_id'] in v.get('deps',{}) and 'chain:'+gps['node_id'] in v.get('deps',{}) and v.get('value',{}).get('carry') is False and type(v.get('value',{}).get('total_horizontal_m')) in (int,float)]
   if candidates:
    meters=max(candidates,key=lambda row:row['version'])['value']['total_horizontal_m']
    unit='米' if '米' in text else '码' if '码' in text else s.get('journey',{}).get('profile',{}).get('units',{}).get('value','码')
    amount=meters/(1 if unit=='米' else .9144)
    return f'上一杆记录的水平总距离约{round(amount/5)*5:g}{unit}，包含滚动，不是Carry。'
 return '上一杆还缺少已确认的起点和落点，暂时算不出距离。地图选点只更新定位，不会自动记成击球。'

def approach_selection(text):
 if re.search(r'用了|打了|刚才|上一杆|[？?]|能不能|可以吗|怎么样|用哪',text):return None
 clean=re.sub(r'[\s，,。！!]','',text)
 m=re.fullmatch(r'(?:好|好的)?(?:那就|我想|我准备|我决定|就|我)?(?:用|选|拿)?(一号木|1号木|三号木|3号木|[2-9二两三四五六七八九](?:号铁|铁))(攻果岭|攻上去|打向果岭中央|打向果岭中心|打向果岭|上果岭)(?:吧)?',clean)
 if not m:return None
 club=selection(m[1])
 if not club:return None
 return dict(club=club['label'],target='green_center' if '中央' in m[2] or '中心' in m[2] else 'green',wording=m[2])

def commit(s,p,chosen):
 j=s['journey'];c=j.get('consultation')
 decision={'club':chosen['club'],'target':chosen['target'],'source':'user_report','event_id':p['event_id'],'hole':fact_value(s,'context.active_hole'),'type':'decision_commitment','execution_confirmed':False}
 if c:
  j['last_consultation']=copy.deepcopy(c);j['last_consultation']['status']='superseded_by_explicit_player_decision';j.pop('consultation',None)
 j.setdefault('player_decisions',[]).append(decision)
 return '好，用'+chosen['club']+chosen['wording']+'，按平常节奏打。'
