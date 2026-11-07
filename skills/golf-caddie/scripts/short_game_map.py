"""Short-game comparison requests are advice, never a player's commitment.
Reference: https://www.pga.com/story/expanding-your-understanding-of-pitching
"""
import re
from round_state import fact_value
from lie_position import infer,fresh_position
from shot_evidence import haversine
from conversation_preferences import agreement

def comparison(text):
 return bool(re.search(r'高飞|高抛|抛切|切滚|切滚球|滚切|低飞|低滚',text) and re.search(r'还是|哪个好|哪种|选哪|怎么选|怎么样|可不可以|能不能|可以吗|好不好|呢|[？?]',text))
def question(text):return bool(re.search(r'[？?]|还是|怎么|如何|哪[支只种个边侧]|多少|多远|是否|有没有|吗|呢',text))
def scope(s):return ((s.get('journey',{}).get('round') or {}).get('id'),fact_value(s,'context.course_snapshot'),fact_value(s,'context.active_hole'))

def handle(s,p,now):
 j=s['journey'];text=p.get('text','');pending=j.get('short_game_question');asked=comparison(text)
 if pending and not asked:
  if pending.get('kind')!='map_obstacle_check':
   from short_game import handle as old_question
   return old_question(s,p,now)
  if text in ('不清楚','不知道','看不清'):
   j.pop('short_game_question',None)
   return '那先不假定地面线路通畅。选你熟悉、能送到宽阔落点的打法，别盲目切滚穿过障碍，也不勉强高抛。'
  blocked=agreement(text,positive=('有','有沙坑','有水','有长草','有障碍','有起伏'),negative=('没有','没有障碍','没有这些','没有挡着'))
  accepted=(not blocked) if blocked is not None else agreement(text,positive=('能','可以滚过去','能滚过去','路很顺','可以切滚'),negative=('不能','不能滚过去'))
  if accepted is not None:
   j.pop('short_game_question',None)
   pos=fresh_position(s,now)
   if tuple(pending['scope'])!=scope(s) or now-pending['at']>300 or not pos or haversine(pending['position'],pos['value'])>max(5,min(15,pending['position']['accuracy_m']+pos['value']['accuracy_m'])):
    return '位置或球洞已经变化，请重新问这杆的打法，我再按当前情况比较。'
   if accepted:
    j['last_short_game_advice']={'type':'system_advice','style':'chip_and_run','event_id':p['event_id'],'source':'user_confirmed_rollable_route','not_player_decision':True}
    return '那我更倾向切滚，用你熟悉的短杆，选果岭上一块平坦落点，让球滚过去；别追贴边旗位。'
   j['last_short_game_advice']={'type':'system_advice','style':'familiar_pitch_or_recovery','event_id':p['event_id'],'source':'user_reported_blocked_route','not_player_decision':True}
   return '那就别走地面切滚路线。优先用你熟悉的抛切越过障碍，落到较宽的果岭区域；没把握就先脱困，不硬打高难度高抛。'
  j.pop('short_game_question',None)
 if not asked:return None
 if s.get('session',{}).get('draft') or any(q.get('status')=='pending' for q in s.get('questions',{}).values()):return '先完成或跳过当前记分，我再和你比较高飞与切滚，避免把回答记错。'
 if j.get('pending_shot_link'):j.setdefault('deferred_shot_links',[]).append(j.pop('pending_shot_link'))
 j.pop('pending_green_followup',None)
 # Repair an old malformed plan without changing any legitimate confirmed decision.
 c=j.get('consultation',{})
 if c.get('player_plan') and question(c['player_plan']):
  c.setdefault('discarded_question_plans',[]).append(c.pop('player_plan'));c['phase']='plan'
 pos=fresh_position(s,now)
 if not pos:return '要比较高飞和切滚，先更新当前位置；刚才的打法讨论保留。'
 inferred=infer(s,now);lie=c.get('lie_report') if c.get('lie_evidence',{}).get('source')=='user_report' else inferred['label'] if inferred else c.get('lie_report')
 j['last_short_game_advice']={'type':'system_advice','event_id':p['event_id'],'not_player_decision':True,'position_version':pos['version']}
 if lie=='沙坑':return '如果球在沙坑，先以脱困为主，不用切滚穿沙沿。选你熟悉的沙坑打法，把球送到较宽的果岭区域，不追旗。'
 if lie=='长草':return '长草会影响触球和滚动，我更倾向熟悉的抛切，先把球送上果岭再滚；别默认用高难度高抛。'
 eid=fact_value(s,'context.course_snapshot');course=s.get('evidence',{}).get(eid,{}).get('data',{})
 hole=next((h for h in course.get('holes',[]) if h['number']==fact_value(s,'context.active_hole')),None)
 greens=[g for g in (hole or {}).get('objects',[]) if g.get('kind')=='green_center']
 if len(greens)==1 and haversine(pos['value'],greens[0])>80:
  return '这距离不适合直接套用果岭边的切滚。先用熟悉的球杆把球送到合适的短杆距离，再按实际球位选打法。'
 from short_game_route import assess
 route=assess(s,now);j['last_short_game_advice']['route_assessment']=route
 if route['verdict']=='clear':
  j.pop('short_game_question',None);j['last_short_game_advice'].update(style='chip_and_run',source='mapped_route')
  return '按地图这条球道接果岭的线路，我倾向切滚，先落在果岭前部再滚动，不追旗。'
 if route['verdict']=='blocked':
  j.pop('short_game_question',None);j['last_short_game_advice'].update(style='familiar_pitch_or_recovery',source='mapped_obstacle')
  names={'bunker':'沙坑','water':'水体','rough':'长草'}
  labels='、'.join(dict.fromkeys(names[v['kind']] for v in route['obstacles']))
  return '地图显示这条路线经过或紧邻'+labels+'，不建议直接切滚。优先用熟悉的抛切，选过障碍后较宽的落点；没把握就先脱困。'
 j['short_game_question']={'kind':'map_obstacle_check','scope':list(scope(s)),'at':now,'position':dict(pos['value']),'event_id':p['event_id']}
 return '地图还不能确认这段地面线路。球到果岭之间有沙坑、长草，或明显起伏挡着吗？'


def explicit_plan(text):
 if question(text) or re.search(r'不想|不要|不打|不确定|不知道|也许|可能|刚才|上一杆|打了|用了',text):return False
 return bool(re.search(r'打向|攻果岭|送上|过渡|切滚|抛切|高飞|高抛|推过去|瞄准',text) and re.search(r'[1-9一二两三四五六七八九](?:号铁|铁|号木)|短杆|切滚|抛切|高飞|高抛|推杆|球杆',text))
