"""Follow-up requests for a more conservative tee alternative."""
import re

def handle(state,text,now,event_id=None,*,save_only=False):
 clean=re.sub(r'[\s，,。！？?!]','',text)
 safer=re.fullmatch(r'(?:还有没有|有没有|还有|有|能不能|可以|换个|换一个|想要|给个|给一个)?(?:更|再|稍微)?(?:安全|稳妥|稳|保守)(?:一?点|些)?(?:的)?(?:方案|策略|打法|路线|选择)?(?:吗|呢)?',clean)
 alternative=re.fullmatch(r'(?:还)?(?:有没有|有|还有|能不能给|可以给|给我|给|看看|换个|换一个)?(?:其它|其他|别的|另外|另一种|另一个)(?:的)?(?:开球)?(?:方案|策略|路线|打法|选择)(?:吗|呢)?',clean)
 from round_state import fact_value,canonical
 j=state.get('journey',{})
 scope=[(j.get('round') or {}).get('id'),fact_value(state,'context.course_snapshot'),fact_value(state,'context.active_hole')]
 pending=j.get('tee_alternative_carry')==scope
 # Accept a complete multi-club answer before the ordinary single-club router.
 pieces=re.split(r'[，,、；;]',text.strip())
 pattern=r'([3三5五]号?木|铁木杆|混合杆|[234二三四]号?铁)[，,：:]?(?:Carry|carry|落地)?(\d{2,3})(码|米)?'
 if pending and len(pieces)>1 and all(re.fullmatch(pattern,re.sub(r'\s','',v)) for v in pieces):
  for piece in pieces:
   handle(state,piece,now,event_id,save_only=True)
  return new_alternative_text('已记录这几支杆的Carry。'+handle(state,'有没有其它方案',now,event_id))
 stable=re.search(r'(?:比较稳[定妥]|最稳|有把握|稳定).*?([35三五]号?木|铁木杆|混合杆)',clean)
 if pending and stable:
  club=stable[1];key='five_wood' if club.startswith(('5','五')) else 'three_wood' if club.startswith(('3','三')) else 'hybrid'
  curve='右曲' if '右曲' in clean else '左曲' if '左曲' in clean else '未知'
  j.setdefault('profile',{})['trusted_tee_club']=dict(value=dict(club_key=key,club_name=club,usual_curve=curve),source='user_report',event_id=event_id)
  j['profile']['fairway_finder']=dict(value=dict(club_key=key,club_name=club),source='user_report',event_id=event_id)
  from tee_strategy import reported_carry_clubs,analyze
  from tee_geometry import tee_targets
  from tee_next_shot_options import compare
  a=analyze(state,now);known=reported_carry_clubs(j.get('profile',{}))
  if a and key in known:
   targets=tee_targets(state,a,[(key,known[key])],allow_crossing=True)
   offer=compare(state,a,targets,j.get('profile',{}).get('units',{}).get('value','码'),requested_alternative=True)
   if offer:
    c=j.setdefault('consultation',{});c.update(last_offer=offer,phase='tee_commit');c.pop('suggestion',None);c.pop('selected_club',None)
    return '记下了，你更有把握用'+club+'，'+('平常有点'+curve+'。' if curve!='未知' else '。')+offer['text']+'仍需按实际左右偏差确认障碍余量，右曲或左曲不代表另一侧不会失误。'
  return '已记录你更有把握用'+club+'。当前地图没有匹配到这支杆的可核对落区，不能据此说它更安全；请确认目标落区宽度和障碍余量。'
 report=re.fullmatch(r'([3三5五]号?木|铁木杆|混合杆|[234二三四]号?铁)[，,：:]?(?:Carry|carry|落地)?(\d{2,3})(码|米)?',clean)
 if pending and report:
  label=report[1];key='three_wood' if label.startswith(('3','三')) and '木' in label else 'five_wood' if label.startswith(('5','五')) else 'hybrid' if label in ('铁木杆','混合杆') else 'iron'+{'二':'2','三':'3','四':'4'}.get(label[0],label[0])
  distance=int(report[2])
  if not 10<=distance<=400:return '请确认这支杆的常态Carry距离。'
  unit=report[3] or j.get('profile',{}).get('units',{}).get('value','码')
  j.setdefault('profile',{})[key]=dict(value=dict(distance=distance,units=unit,distance_type='carry'),source='user_report',event_id=event_id)
  if save_only:return ''
  return new_alternative_text('已记录'+label+'Carry约'+str(distance)+unit+'。'+handle(state,'有没有其它方案',now,event_id))
 if not (safer or alternative):return None
 from tee_strategy import analyze,reported_carry_clubs
 a=analyze(state,now)
 if not a or a['par'] not in (4,5):return None
 j=state['journey'];known=reported_carry_clubs(j.get('profile',{}))
 finder=j.get('profile',{}).get('fairway_finder',{}).get('value') or {}
 if finder.get('club_key') and finder['club_key'] not in known:
  j['tee_alternative_carry']=scope
  return '你设置的保底开球杆是'+finder['club_name']+'。这支杆的稳定Carry大概多少？可以报杆名和距离，我再核对保守落区。'
 if not pending and not any(k in known for k in ('three_wood','five_wood','hybrid','long_iron','iron3','iron4')):
  j['tee_alternative_carry']=scope
  return ('可以，先比较沙前或更宽的落区，同时看下一杆剩余距离。' if safer else '可以，换一支杆或落区一起比较，同时看下一杆剩余距离。')+'你有3号木、5号木或铁木杆吗？各自稳定Carry大概多少？可一次报多支；没有的说没有，不清楚可以跳过。'
 from tee_geometry import tee_targets
 from tee_next_shot_options import compare
 targets=tee_targets(state,a,list(known.items()),allow_crossing=True)
 unit=j.get('profile',{}).get('units',{}).get('value','码')
 offer=compare(state,a,targets,unit,requested_alternative=True)
 j['tee_alternative_carry']=scope
 if not offer:return '现有地图和杆距尚未核对到更保守的落区，请补充其他球道木、铁木杆或长铁的Carry，再比较。'
 if len(offer.get('options',[]))<2:return '按现有地图和杆距，暂未核对到风险更低且有足够落区余量的另一方案。你还有其他球道木、铁木杆或长铁吗？可以补充稳定Carry，以及你最有把握的开球杆和通常左右偏差，我再比较。'
 c=j.get('consultation')
 previous=(c or {}).get('last_offer') or {}
 def identity(option):return (option.get('club_key') or option.get('club'),option.get('carry_yards'),canonical(option.get('aim_point')))
 shown={identity(o) for o in previous.get('options',[])} if previous.get('comparison_context')==offer.get('comparison_context') and offer.get('comparison_context') is not None else set()
 if shown and offer.get('options') and all(identity(o) in shown for o in offer['options']):
  names='、'.join(dict.fromkeys(o.get('club','') for o in previous.get('options',[]) if o.get('club')))
  return '刚才已介绍'+names+'，目前没有核对到不同且有实际取舍的新方案。可以继续比较已给出的选项；如果你想换一个具体落区或球杆，也可以直接告诉我。'
 if c is not None:c.update(last_offer=offer,phase='tee_commit');c.pop('suggestion',None);c.pop('selected_club',None)
 return new_alternative_text(offer['text']+'你想选哪支杆？')

def new_alternative_text(text):
 """Keep the full selectable offer in state, but avoid repeating driver narration."""
 lines=text.split('\n')
 if len(lines)<2 or not any('方案：Carry' in line and '一号木方案：' not in line for line in lines):return text
 first=lines[0]
 prefix=first.split('一号木方案：',1)[0] if '一号木方案：' in first else ''
 kept=[line for line in lines if '一号木方案：' not in line]
 if len(kept)==1:
  kept[0]=kept[0].replace('方案：Carry','Carry').replace('你想选哪支杆？','你想用这支杆吗？')
 return prefix+'\n'.join(kept)
