"""Concise approach dialogue; simulated selection is not real-world shot evidence."""
import copy,re
from lie_position import fresh_position,infer
from round_state import fact_value
from approach_strategy import advise as detailed_advise,requested as previous_requested

def requested(text):
 return previous_requested(text) or bool(re.search(r'(?:用|选|拿)(?:哪|那)(?:一)?(?:支|只|个)?杆|选杆建议',text))

def prepare(s,c,now):
 pos=fresh_position(s,now)
 eid=fact_value(s,'context.course_snapshot')
 course=s.get('evidence',{}).get(eid,{}).get('data',{})
 simulated=bool(pos and course.get('reference_simulation') is True and pos['value'].get('simulation_source')=='map_click' and pos['value'].get('simulation_hole')==fact_value(s,'context.active_hole'))
 if simulated:
  c['ball_position_report']='simulation_selected'
  c['ball_position_evidence']={'source':'map_click_simulation','position_version':pos['version'],'not_real_shot_evidence':True}
 if c.get('ball_position_report') in ('user_confirmed','simulation_selected'):
  inferred=infer(s,now)
  if inferred and (not c.get('lie_report') or c.get('lie_evidence',{}).get('source')=='gps_course_surface'):
   c['lie_report']=inferred['label'];c['lie_evidence']=inferred
 return pos

def advise(s,c,now):
 calc=copy.deepcopy(c)
 if calc.get('ball_position_report')=='simulation_selected':calc['ball_position_report']='user_confirmed'
 out=detailed_advise(s,calc,now);out['detail_text']=out['text']
 from speech_presentation import spoken_text
 text=spoken_text(out['text'])
 text=re.sub(r'(?:OB参考点|障碍参考点)距设备约[0-9.]+(?:码|米)；','',text)
 text=text.replace('这些不是障碍近沿或远沿，不能据此判断能否跨越，也不能证明路线安全。','障碍边界未确认，别勉强飞越。')
 text=text.replace('这是设备位置距离，尚未确认就是球位。','')
 text=text.replace('还没有可用的7铁Carry，先不硬指定杆号。','先用熟悉的球杆分段推进。')
 out['text']=text
 out['position_provenance']=c.get('ball_position_evidence',{})
 return out
