"""Provisional numbered-iron distances; never persist as observed ability."""
import re
from round_state import fact_value
from lie_position import fresh_position,infer
from shot_evidence import haversine

def iron_table(profile):
 seven=profile.get('seven',{}).get('value',{})
 if seven.get('distance_type')!='carry' or seven.get('units') not in ('码','米') or type(seven.get('distance')) not in (int,float) or not 0<seven['distance']<=400:return {}
 baseline=seven['distance']/(.9144 if seven['units']=='米' else 1)
 table={n:{'carry_yards':baseline+(7-n)*10,'source':'estimated_10_yard_gap' if n!=7 else 'user_report'} for n in range(2,10) if baseline+(7-n)*10>0}
 # A separately reported numbered iron overrides the provisional gap estimate.
 long=profile.get('long_iron',{}).get('value',{});match=re.fullmatch(r'([2-9])(?:号铁|铁)',long.get('club_name') or '')
 if match and long.get('distance_type')=='carry' and long.get('units') in ('码','米') and type(long.get('distance')) in (int,float) and 0<long['distance']<=400:
  table[int(match[1])]={'carry_yards':long['distance']/(.9144 if long['units']=='米' else 1),'source':'user_report'}
 return table

def pitching_wedge(profile,irons):
 value=profile.get('pitching_wedge',{}).get('value',{})
 if value.get('distance_type')=='carry' and value.get('units') in ('码','米') and type(value.get('distance')) in (int,float) and 0<value['distance']<=400:
  return {'carry_yards':value['distance']/(.9144 if value['units']=='米' else 1),'source':'user_report'}
 if 9 in irons and irons[9]['carry_yards']>10:
  return {'carry_yards':irons[9]['carry_yards']-10,'source':'estimated_pitching_wedge_gap'}
 return None

def parse_wedge_range(text,unit):
 match=re.fullmatch(r'(\d{1,3})\s*(码|米)?\s*[-–—~～到至]\s*(\d{1,3})\s*(码|米)?',text.strip())
 if not match or not 1<=int(match[1])<=int(match[3])<=250 or (match[2] and match[4] and match[2]!=match[4]):
  return None
 return {'low':int(match[1]),'high':int(match[3]),'units':match[4] or match[2] or unit}

def parse_wedge_bag(text,unit):
 text=re.sub(r'^有\s*','',text.strip()).rstrip('。！!')
 pieces=re.split(r'\s*(?:[，,、；;]|和)\s*|\s+(?=\d{2}度)',text)
 if len(pieces)==1 and re.fullmatch(r'\d{2}(?:\s+\d{2})+',text):pieces=text.split()
 lofts=[];ranges={}
 for piece in pieces:
  match=re.fullmatch(r'(\d{2})(?:度(?:杆)?)?(?:[：: ]*([0-9].*))?',piece.strip())
  if not match or not 48<=int(match[1])<=64:return None
  loft=match[1]
  if match[2]:
   value=parse_wedge_range(match[2],unit)
   if not value or (loft in ranges and ranges[loft]!=value):return None
   ranges[loft]=value
  if int(loft) not in lofts:lofts.append(int(loft))
 return lofts,ranges

def parse_spoken_wedge_bag(text, unit):
 # An unqualified 48–64 token starts a club. Use a unit for a single Carry.
 pieces = re.split(r'[，,、；;]', text.strip().rstrip('。！!'))
 lofts, ranges, uses = [], {}, {}
 loft = None
 for piece in pieces:
  piece = piece.strip()
  named = re.fullmatch(r'(4[6-9]|5[0-9]|6[0-4])(?:度(?:杆)?)?', piece)
  if named:
   loft = named[1]
   if int(loft) not in lofts:
    lofts.append(int(loft))
   continue
  if loft is None:
   return None
  if piece in ('沙坑','打沙坑','沙坑用'):
   uses[loft] = '沙坑'
   continue
  value = parse_wedge_range(piece, unit)
  single = re.fullmatch(r'(\d{1,3})\s*(码|米)', piece)
  zero_range = re.fullmatch(r'0\s*(?:到|至|[-–—~～])\s*(\d{1,3})\s*(码|米)?', piece)
  if single and 1 <= int(single[1]) <= 250:
   value = {'low': int(single[1]), 'high': int(single[1]), 'units': single[2]}
  if zero_range and 1 <= int(zero_range[1]) <= 250:
   value = {'low': 0, 'high': int(zero_range[1]), 'units': zero_range[2] or unit}
  if not value or (loft in ranges and ranges[loft] != value):
   return None
  ranges[loft] = value
 return (lofts, ranges, uses) if lofts else None


def lofted_wedge_option(profile,distance):
 candidates=[]
 for loft,value in profile.get('lofted_wedge_ranges',{}).get('value',{}).items():
  scale=1/.9144 if value['units']=='米' else 1
  low,high=value['low']*scale,value['high']*scale
  if low<=distance<=high:candidates.append((abs((low+high)/2-distance),int(loft),low,high))
 return min(candidates) if candidates else None

def back_pin_option(profile, distance, *, landing=None):
 """Select a carry window short of the estimated back pin."""
 low, high = distance-10, distance-5
 if landing:
  low=max(low,landing[0]);high=min(high,landing[1])
 if low <= 0 or low>high:return None
 table=iron_table(profile)
 wedge=pitching_wedge(profile,table)
 clubs=[(f'{n}号铁',v['carry_yards'],v['carry_yards'],v['source']) for n,v in table.items()]
 if wedge:clubs.append(('P杆',wedge['carry_yards'],wedge['carry_yards'],wedge['source']))
 for loft,value in profile.get('lofted_wedge_ranges',{}).get('value',{}).items():
  divisor=.9144 if value['units']=='米' else 1
  clubs.append((f'{loft}度杆',value['low']/divisor,value['high']/divisor,'user_report'))
 unit=profile.get('units',{}).get('value','码')
 scale=.9144 if unit=='米' else 1
 target=f'{round(low*scale)}–{round(high*scale)}{unit}'
 matching=[(abs(carry-(low+high)/2),label,carry,source)
           for label,minimum,maximum,source in clubs if minimum<=high+1e-8 and maximum>=low-1e-8
           for carry in [min(maximum,max(minimum,(low+high)/2))]]
 if matching:
  _,club,carry,source=min(matching)
  basis='按自报杆距' if source=='user_report' else '按现有杆距估算'
  wording=f'后旗留前滚空间，目标Carry约{target}。可考虑{club}，{basis}，把落点放在旗前。'
 else:
  longer=[(maximum,label,source) for label,_,maximum,source in clubs if maximum>=high]
  if longer:
   _,club,source=min(longer)
   carry=(low+high)/2
   wording=f'后旗目标Carry约{target}。可考虑{club}收着打，前提是你熟悉这个挥幅的Carry。'
   return wording,{'club':club,'target_carry_yards':carry,'source':source,'status':'candidate','not_for_learning':True}
  return f'后旗目标Carry约{target}，现有杆距资料不足以给具体候选。',None
 return wording,{'club':club,'target_carry_yards':carry,'source':source,'status':'candidate','not_for_learning':True}


def present_iron_option(state,text,now,*,pin=None, strategy=False, verified_lines=False):
 phrases=('建议用熟悉的短杆控制距离。','建议用熟悉的球杆分段推进，别靠额外发力硬攻。')
 back=bool(strategy and pin and pin.get('depth')=='后')
 if not back and not any(p in text for p in phrases) or not (pin or re.search(r'到果岭(?:中心|参考点)约',text)):return text,None
 pos=fresh_position(state,now)
 if not pos:return text,None
 c=state.get('journey',{}).get('consultation') or {}
 if c.get('lie_report') in ('长草','沙坑','不清楚') or '先保证脱困' in text:return text,None
 profile=state.get('journey',{}).get('profile',{});table=iron_table(profile)
 wedge=pitching_wedge(profile,table)
 if wedge:table['P杆']=wedge
 if pin:
  distance=(pin['min_m']+pin['max_m'])/2/.9144
 else:
  course=state.get('evidence',{}).get(fact_value(state,'context.course_snapshot'),{}).get('data',{})
  hole=next((h for h in course.get('holes',[]) if h['number']==fact_value(state,'context.active_hole')),None)
  greens=[o for o in (hole or {}).get('objects',[]) if o['kind']=='green_center']
  if len(greens)!=1:return text,None
  distance=haversine(pos['value'],greens[0])/.9144
 if back and c.get('lie_report') in ('球道','发球台'):
  if verified_lines:
   from short_pin_distance import estimate,pin_distance_wording
   from hazard_route import landing_line
   aimed=estimate(state,now,short_game_only=False,include_aim=True)
   line=landing_line(state,now,aimed['aim'],corridor=True) if aimed and aimed.get('aim') else None
   option=None
   if line:
    margin=max(line['accuracy_m'],3*.9144)
    far=max((v for v in line['hazards'].values() if v is not None),default=0)
    landing=(max(line['front_m'],far)+margin,line['back_m']-margin)
    option=back_pin_option(profile,line['target_m']/.9144,landing=tuple(v/.9144 for v in landing))
   if not option:
    prefix=pin_distance_wording(pin,profile.get('units',{}).get('value','码'))
    return prefix+'。旗前的落点或飞越余量不足，含瞄准线两侧的障碍风险，先找果岭宽处的可用线路；没有把握就分段打。',None
   wording,candidate=option
   prefix=pin_distance_wording(pin,profile.get('units',{}).get('value','码'))
   coverage='' if line.get('hazard_coverage_complete') else '先确认地图未覆盖的障碍，现场确认能过再用。'
   return prefix+'。按旗区代表点这条线，'+wording+coverage,candidate
  option=back_pin_option(profile,distance)
  if option:
   wording,candidate=option
   text=re.sub(r'(?:可考虑[^。]*(?:果岭中央|候选)[^。]*|建议用熟悉的短杆控制距离|建议用熟悉的球杆分段推进，别靠额外发力硬攻)。', '', text)
   return text+wording,candidate
 if c.get('lie_report') in ('球道','发球台'):
  from wedge_leave import suggested_combination
  combo=suggested_combination(state.get('journey',{}),distance)
  if combo:
   unit=profile.get('units',{}).get('value','码');scale=.9144 if unit=='米' else 1
   finish=round(combo['median_finish_yd']*scale)
   wording=(f'按你在相近距离报告的{combo["samples"]}杆实绩，可先考虑{combo["club"]}{combo["swing"]}'
            f'，一杆后离旗中位数约{finish}{unit}。先核对这杆的飞越距离和落点。')
   for phrase in phrases:text=text.replace(phrase,wording)
   return text,{**combo,'source':'reported_wedge_outcomes','status':'candidate','not_for_learning':True}
 angle=lofted_wedge_option(profile,distance)
 if angle:
  _,loft,low,high=angle
  unit=profile.get('units',{}).get('value','码');scale=.9144 if unit=='米' else 1
  club=f'{loft}度杆'
  wording=f'可考虑{club}，你自报的Carry约{round(low*scale)}–{round(high*scale)}{unit}，瞄果岭较宽处。'
  for phrase in phrases:text=text.replace(phrase,wording)
  return text,{'club':club,'carry_range_yards':[low,high],'source':'user_report','status':'candidate','not_for_learning':True}
 if not table or not min(v['carry_yards'] for v in table.values())-5<=distance<=max(v['carry_yards'] for v in table.values())+5:
  ranges=profile.get('lofted_wedge_ranges',{}).get('value',{})
  if not ranges:return text,None
  eligible=[(entry['carry_yards'],f'{number}号铁' if isinstance(number,int) else number,entry['source'])
            for number,entry in table.items() if entry['carry_yards']+1e-8>=distance]
  for loft,value in ranges.items():
   maximum=value['high']/(.9144 if value['units']=='米' else 1)
   if maximum+1e-8>=distance:eligible.append((maximum,f'{loft}度杆','user_report'))
  option=None
  if eligible and c.get('lie_report') in ('球道','发球台'):
   carry,club,source=min(eligible)
   unit=profile.get('units',{}).get('value','码');scale=.9144 if unit=='米' else 1
   basis='按自报距离' if source=='user_report' else '按现有杆距估算'
   wording=(f'可考虑{club}控制挥杆，{basis}Carry约{round(carry*scale)}{unit}，'
            f'把Carry控到约{round(distance*scale)}{unit}。确认你熟悉这个挥幅，并给飞越和落点留余量。')
   option={'club':club,'carry_yards':carry,'target_carry_yards':distance,'source':source,
           'status':'candidate','not_for_learning':True}
  else:
   wording='已知的常态Carry和角度杆范围都未覆盖这个距离。可用你熟悉且有把握的控制挥杆，或先打到宽处。'
  for phrase in phrases:text=text.replace(phrase,wording)
  return text,option
 # Treat a sub-yard rounding difference as a tie, then favor room for rollout.
 number=min(table,key=lambda n:(round(abs(table[n]['carry_yards']-distance),1),table[n]['carry_yards']))
 entry=table[number];unit=profile.get('units',{}).get('value','码');scale=.9144 if unit=='米' else 1
 amount=round(entry['carry_yards']*scale)
 club=f'{number}号铁' if isinstance(number,int) else number
 basis={'estimated_pitching_wedge_gap':'暂按比9号铁短约10码估算','estimated_10_yard_gap':'按7铁每号相差10码估算'}.get(entry['source'],'按你自报的距离')
 wording=f'可考虑{club}，{basis}，Carry约{amount}{unit}，目标取果岭中央。'
 if 0.5<=distance-entry['carry_yards']<=5.05:
  wording+='落地后还可能前滚，实际滚动看现场球况。'
 journey=state.get('journey',{})
 preference=profile.get('shot_style_preferences',{}).get('between_clubs',{}).get('value')
 if journey.get('memory_allowed') is True and preference and c.get('lie_report') in ('球道','发球台'):
  shorter=[n for n,v in table.items() if 0<distance-v['carry_yards']<=10]
  longer=[n for n,v in table.items() if 0<v['carry_yards']-distance<=10]
  if shorter and longer:
   options=shorter if preference=='短一号正常挥' else longer
   preferred=min(options,key=lambda n:abs(table[n]['carry_yards']-distance))
   label=f'{preferred}号铁' if isinstance(preferred,int) else preferred
   if preference=='短一号正常挥':
    wording=f'按你平时短一号正常挥的习惯，可先看{label}。确认Carry够飞过前方障碍，落地也有前滚空间时再用。'+wording
   else:
    wording=f'按你平时长一号收着打的习惯，可先看{label}。确认你熟悉这支杆收着打的Carry，且落点有余量时再用。'+wording
 for phrase in phrases:text=text.replace(phrase,wording)
 return text,{'club':club,**entry,'status':'candidate','not_for_learning':True}
