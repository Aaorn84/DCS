"""Evidence-bounded approach options. Point hazards never imply safe crossing edges."""
import re,math
from lie_position import fresh_position,infer
from round_state import fact_value
from shot_evidence import haversine

def requested(text):
 return bool(re.search(r'怎么打|如何打|风险|策略|怎么选杆|用什么杆|选什么杆|该用哪|注意什么|如何进攻|能攻吗|能上吗|怎么避|安全路线',text))

def advise(s,c,now):
 unit=s.get('journey',{}).get('profile',{}).get('units',{}).get('value','码');scale=1 if unit=='米' else 1/.9144
 pos=fresh_position(s,now);eid=fact_value(s,'context.course_snapshot');e=s['evidence'].get(eid,{})
 hole=next((h for h in e.get('data',{}).get('holes',[]) if h['number']==fact_value(s,'context.active_hole')),None) if e.get('active') and e.get('phase')=='final' else None
 out={'text':'','position_version':pos['version'] if pos else None,'course_evidence':eid,'suggestion':None,'risks':[]}
 if not pos or not hole:
  out['text']='目前缺少可靠定位或地图，不能给准确码数和定位选杆。先选自己熟悉、能稳定送回可打区域的打法，避免勉强跨越现场障碍。';return out
 greens=[o for o in hole['objects'] if o['kind']=='green_center']
 if len(greens)!=1:out['text']='果岭目标资料不完整，暂不选具体攻果岭杆号。';return out
 d=haversine(pos['value'],greens[0]);out['distance_m']=d
 text=f'到果岭中心约{round(d*scale/5)*5:g}{unit}。'
 confirmed=c.get('ball_position_report')=='user_confirmed'
 lie=c.get('lie_report')
 if not confirmed:text+='这是设备位置距离，尚未确认就是球位。'
 if lie:text+='按'+lie+'球位考虑。'
 profile=s.get('journey',{}).get('profile',{});seven=profile.get('seven',{}).get('value',{})
 carry=seven.get('distance');valid=isinstance(carry,(int,float)) and not isinstance(carry,bool) and 0<carry<=400 and seven.get('distance_type')=='carry' and seven.get('units') in ('码','米')
 if valid:
  meters=carry*(.9144 if seven['units']=='码' else 1)
  text+=f'你的自报7铁Carry约{round(meters*scale):g}{unit}。'
  if (not confirmed or lie=='球道') and abs(d-meters)<=max(8,meters*.08):
   text+=('若设备就在球旁且是球道球位，' if not confirmed else '')+'7铁可以作为攻果岭的候选，先考虑果岭中央这一参考目标，不盲目追旗。';out['suggestion']={'club':'7号铁','target':'green_center','status':'candidate','source':'self_reported_carry_comparison'}
  elif d>meters*1.08:text+='这比你的7铁常态Carry更远，不建议靠额外发力硬补；可比较更长且熟悉的杆与分段过渡。'
  else:text+='这比7铁常态Carry短，不默认用7铁全挥；优先比较你熟悉的短杆或控制距离打法。'
 else:text+='还没有可用的7铁Carry，先不硬指定杆号。'
 if lie in ('长草','沙坑','不清楚'):text+='这种球位会增加触球和距离的不确定性，先保证脱困，不承诺按球道Carry飞越障碍。'
 hazards=[o for o in hole['objects'] if o['kind'] in ('hazard_reference','ob_reference')]
 if hazards:
  refs=sorted(hazards,key=lambda o:haversine(pos['value'],o))[:2]
  for o in refs:
   amount=round(haversine(pos['value'],o)*scale/5)*5
   label='OB参考点' if o['kind']=='ob_reference' else '障碍参考点'
   text+=f'{label}距设备约{amount:g}{unit}；'
   out['risks'].append({'object_id':o['id'],'kind':o['kind'],'distance_m':haversine(pos['value'],o),'geometry':'point_only'})
  text+='这些不是障碍近沿或远沿，不能据此判断能否跨越，也不能证明路线安全。'
 else:text+='地图缺少完整障碍范围，暂不能确认左右或前后的安全余量。'
 if profile.get('usual_miss',{}).get('value') in ('偏右','偏左'):text+='你常见'+profile['usual_miss']['value']+'，选目标时要为这个偏差留空间，不只靠反向瞄准抵消。'
 text+='风、高差、滚动和实际散布尚未计入；果岭中央也不等于已验证安全区。'
 out['text']=text;return out
