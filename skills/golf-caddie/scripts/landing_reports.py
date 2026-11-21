"""Scoped player landing observations; no inferred distance or penalty."""
import re,copy
from round_state import canonical
from shot_links import scope

def parse(text):
 clean=re.sub(r'[，,。！!？?\s]','',text.lower())
 correction=bool(re.match(r'刚才看错了|看错了|更正|不是',clean))
 clean=re.sub(r'^(?:刚才看错了|看错了|更正一下|更正)','',clean)
 if clean.startswith('不是') and '是' in clean[2:]:clean=clean.rsplit('是',1)[-1]
 clean=re.sub(r'^(?:我看到了|看到了|看到球了|看见球了|看见了)','',clean)
 uncertain=bool(re.search(r'可能|好像|应该|大概|不确定|附近|没看清|没看见|没看到|看不到|看不清|找不到|没找到|只看到',clean.replace('果岭附近','果岭边')))
 if re.search(r'有没有(?:出界|越界)',clean):return dict(kind='hazard',cause='ob',uncertain=True,correction=correction)
 if re.search(r'没出界|没有出界|没越界|没有越界|在界内',clean):
  if not re.search(r'球道|长草|沙坑|果岭',clean):return dict(kind='boundary',uncertain=uncertain,correction=correction)
 elif re.search(r'ob|出界|越界|下水|进水|罚杆区',clean):
  cause='water' if re.search(r'下水|进水|罚杆区',clean) else 'ob'
  return dict(kind='hazard',cause=cause,uncertain=uncertain,correction=correction)
 if re.search(r'确认遗失|确定遗失|可能找不到|可能遗失',clean):return dict(kind='hazard',cause='lost',uncertain=uncertain,correction=correction)
 if clean in ('','球在','在','找到了','能找到','看得到','看到球了'):
  return dict(kind='seen',correction=correction)
 side=next((label for pattern,label in [('左','左侧'),('右','右侧'),('中间|中央','中间')] if re.search(pattern,clean)),None)
 from landing_types import fields
 boundary_uncertain=bool(re.search(r'应该没出界|不确定.*界',clean))
 # Specific ground types take precedence over nearby landmarks.
 kind=next((v for pattern,v in [('沙坑|进坑|掉坑','bunker'),('长草|进草|浅草|草.*深','rough'),('果岭环|果岭裙|停在环上','fringe'),('球道','fairway')] if re.search(pattern,clean)),None)
 if kind:
  lie={'bunker':'沙坑','rough':'长草','fringe':'果岭附近','fairway':'球道'}[kind]
  return dict(kind='lie',lie=lie,side=side,uncertain=uncertain,correction=correction,boundary_uncertain=boundary_uncertain,**fields(clean,kind,side,uncertain,boundary_uncertain))
 if re.search(r'没上去|果岭外|过了果岭|前沿',clean):
  return dict(kind='lie',lie='果岭附近',side=side,uncertain=uncertain,correction=correction,**fields(clean,'unknown',side,uncertain))
 if clean in ('上去了','上了','攻上去了'):return dict(kind='context_green',correction=correction)
 if re.search(r'果岭边|果岭附近|果岭(?:左|右)(?:边|侧)',clean) and not re.search(r'果岭上|果岭内',clean):
  return dict(kind='green_edge',lie='果岭附近',side=side,uncertain=uncertain,correction=correction,**fields(clean,'unknown',side,uncertain))
 if re.search(r'果岭|上果岭',clean):
  return dict(kind='lie',lie='果岭',side=side,uncertain=uncertain,correction=correction,**fields(clean,'green',side,uncertain))
 if clean in ('未知','不清楚','不知道','不确定球位') or uncertain or re.search(r'往[左右]飞|落下后',clean):return dict(kind='unknown',uncertain=True,correction=correction)
 return None

def handle(state,event,now):
 j=state['journey'];audio=j.get('shot_audio',{});key=canonical(scope(state))
 recent=audio.get('asked_arm_id',audio.get('arm_id'))==audio.get('arm_id') and audio.get('scope')==key and 0<=now-audio.get('asked_at',-100000)<=600
 pending=j.get('landing_observation',{});from ball_rules import current
 opening=(current(state) or {}).get('open_shot',{})
 if pending.get('scope')==key and pending.get('stroke_id') and pending['stroke_id']==opening.get('stroke_id') and pending.get('arm_id')==audio.get('arm_id'):recent=True
 if not recent:return None
 row=parse(event.get('text',''))
 if not row:return None
 from ball_rules import blocking,confirm_normal_shot,handle as rules
 if row['kind']=='hazard':
  cause={'water':'下水','ob':'出界','lost':'遗失'}[row['cause']]
  wording=('可能找不到' if row['cause']=='lost' and row['uncertain'] else ('可能' if row['uncertain'] else '确认')+cause)
  if row['correction']:wording='刚才看错了，原球'+('可能'+cause if row['uncertain'] else cause)
  return rules(state,event,wording,now)
 if row['kind']=='boundary' and not row.get('uncertain') and blocking(state):
  return rules(state,event,'刚才看错了，原球在界内' if row.get('correction') else '原球在界内',now)
 if blocking(state):return None
 if row['kind']=='boundary':
  if row.get('correction'):
   corrected=rules(state,event,'刚才看错了，原球在界内',now)
   if corrected is not None:return corrected
  if row['uncertain']:return '先保留边界不确定的情况，不记作已出界或已在界内。请按现场边界确认球的位置。'
  return '记下了，原球在界内。球是在球道、长草、沙坑，还是果岭？'
 if row['kind']=='green_edge':
  confirm_normal_shot(state,event,now)
  save_observation(state,event,row,now)
  return '记下了果岭边这个区域，球位类型还没确定。球在果岭以内，还是果岭环、长草或沙坑？可以继续说“果岭环”或“果岭边长草”。'
 if row['kind']=='context_green':
  decision=(j.get('player_decisions') or [{}])[-1]
  if decision.get('target') not in ('green','green_center'):return '你是说球已经上果岭了吗？'
  from landing_types import fields
  row.update(kind='lie',lie='果岭',side=None,uncertain=False,**fields('果岭上','green'))
 if row['kind']=='unknown' or row.get('uncertain') and not row.get('boundary_uncertain'):
  save_observation(state,event,row,now)
  return '记下你看到的方向或大致位置，落点还未确认；这不等于遗失、出界或下水。到附近再确认球在哪里。'
 confirm_normal_shot(state,event,now)
 if row['kind']=='seen':
  save_observation(state,event,row,now)
  return '好，已经看到球；球位和是否在界内还未确认。需要时告诉我球在哪里。'
 from lie_position import fresh_position
 pos=fresh_position(state,now)
 from ball_rules import current
 flow=current(state) or {};opening=flow.get('open_shot') or {}
 stroke=next((item for item in flow.get('sequence',[]) if item['id']==opening.get('stroke_id')),{})
 from landing_types import normalize,compact,label
 location=normalize(row)
 j['reported_landing']=dict(stroke_id=stroke.get('id'),scope=key,lie=row['lie'],side=row.get('side'),text=event['text'],event_id=event['event_id'],at=now,position=copy.deepcopy(stroke.get('landing')),**{k:v for k,v in location.items() if k!='side'})
 stroke['landing_report']=compact(j['reported_landing']);stroke['landing_location']=location
 j.pop('landing_observation',None)
 audio['phase']='idle'
 prefix='已更正这杆落点，' if row.get('correction') else '记下了，'
 note='边界仍待现场确认。' if row.get('boundary_uncertain') else ''
 return prefix+'球在'+label(location)+'。'+note+('球位类型还未确认，可以继续补充果岭环、长草或沙坑。' if location['lie_type']=='unknown' else '到球旁需要建议时问我。')


def save_observation(state,event,row,now):
 from landing_types import normalize,compact
 from ball_rules import current
 j=state['journey'];flow=current(state) or {};opening=flow.get('open_shot') or {}
 stroke=next((v for v in flow.get('sequence',[]) if v.get('id')==opening.get('stroke_id')),None)
 location=normalize(dict(row,source='user_report',confirmation='pending'))
 report=dict(row,scope=canonical(scope(state)),event_id=event['event_id'],at=now,arm_id=j.get('shot_audio',{}).get('arm_id'),stroke_id=stroke.get('id') if stroke else None,**{k:v for k,v in location.items() if k not in row})
 j['landing_observation']=report
 if stroke is not None:
  stroke['landing_report']=compact(dict(report,confirmation='pending'));stroke['landing_location']=dict(location,confirmation='pending')
  j.pop('reported_landing',None)

def bind_position(state,stroke,point):
 from landing_types import normalize,compact
 j=state['journey'];report=j.get('reported_landing') or {};key=canonical(scope(state))
 if report.get('stroke_id')==stroke.get('id') and report.get('scope')==key:
  report['position']=copy.deepcopy(point)
  stroke['landing_report']=compact(report);stroke['landing_location']=normalize(report)
  return
 pending=j.get('landing_observation') or {};audio=j.get('shot_audio',{})
 from ball_rules import current
 opening=(current(state) or {}).get('open_shot',{})
 if (pending.get('scope')==key and pending.get('arm_id')==audio.get('arm_id')
     and (pending.get('stroke_id')==stroke.get('id') or opening.get('stroke_id')==stroke.get('id'))):
  pending['stroke_id']=stroke['id'];stroke['landing_report']=compact(dict(pending,confirmation='pending'));stroke['landing_location']=normalize(dict(pending,confirmation='pending'))
  return
 eid=scope(state)[1];course=state.get('evidence',{}).get(eid,{}).get('data',{});hole=next((h for h in course.get('holes',[]) if h['number']==scope(state)[2]),None)
 if hole:
  from shot_landing_evidence import classify
  evidence=classify(state,hole,dict(stroke,landing=point))
  if evidence and evidence['source']=='map_geometry':stroke['landing_location']=dict(lie_type=evidence['kind'],area='greenside' if evidence['kind']=='fringe' else None,source='map_geometry',confirmation='pending',green_status='unknown')
