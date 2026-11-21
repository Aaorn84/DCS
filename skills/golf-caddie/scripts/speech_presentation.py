"""User-facing copy policy; does not mutate evidence, decisions or replay journals."""
import re,math
OMIT=(
 '风、滚动和个人散布尚未计入，仍要留余量。',
 '风、滚动和个人散布未计入，落区宽度不能替代命中概率；未标障碍也不证明无障碍。',
 '风、高差、滚动和实际散布尚未计入；果岭中央也不等于已验证安全区。',
)
def natural_tee_options(value,route_details=None):
 # Render only the complete two-route offer; stored events retain their original copy.
 pattern=r'保守：([^\n]+?)约([0-9.]+)(码|米)，瞄落区([^，]+)，预计下一杆约([0-9.]+)(?:码|米)；([^\n]+)。\n进取：([^\n]+?)约([0-9.]+)(码|米)，瞄落区([^，]+)，预计下一杆约([0-9.]+)(?:码|米)；([^\n]+)。\n预计距离以实际落点为准。今天想走哪条？'
 match=re.fullmatch(pattern,value)
 if not match:return value
 c,carry,unit,target,left,risk,a,acarry,aunit,atarget,aleft,arisk=match.groups()
 def detail(kind,unit,risk):
  facts=(route_details or {}).get(kind)
  if not facts:return risk
  for excluded in facts.get('outside_window',[]):
   labels='沙坑' if excluded=='bunker' else '(?:水障碍|水体|水塘|湖|河)'
   risk=re.sub(r'(?:左侧|右侧|前方)?'+labels+'(?:、)?','',risk)
   risk=risk.strip('，、')
   if risk=='要留意偏向障碍的失误':risk='方向要稳住'
  scale=.9144 if unit=='米' else 1
  width=round(facts['width_yards']*scale)
  if '落区' not in risk:risk=f'落区约{width}{unit}宽，'+risk
  for hazard_kind,label in (('bunker','沙坑'),('water','水障碍')):
   hazard=facts.get(hazard_kind)
   if hazard:
    risk=risk.replace('要留意偏向障碍的失误',f'要留意偏向{label}的失误')
    risk=risk.replace('避开这段已知障碍',f'避开这段{label}')
    divisor=1 if unit=='米' else .9144
    near=math.floor(hazard['near_m']/divisor/5)*5
    far=math.ceil(hazard['far_m']/divisor/5)*5
    for old_side in hazard.get('mapped_sides',[]):
     risk=risk.replace(old_side+label,hazard['side']+label)
     if hazard_kind=='water':risk=risk.replace(old_side+'水体',hazard['side']+'水体')
    carry=hazard['carry_yards'];near_yards=hazard['near_m']/.9144;far_yards=hazard['far_m']/.9144
    # 15 yards is a provisional warning band, never a guaranteed safe margin.
    if carry<=far_yards:
     risk+=f"。朝{hazard['side']}这个{label}方向约{near}{unit}到前沿"
     if carry>=near_yards:
      risk+=f"，这支杆的常态Carry会落在{label}范围内，不建议朝{label}方向打，可考虑另一条方案"
     elif near_yards-carry<=15:
      risk+=f"，预计落点离前沿较近，球滚动后有进入{label}的风险，建议避开这个方向，或考虑另一条方案"
     else:risk+=f'，球滚动后有进入{label}的风险'
    else:
     risk+=f"。朝{hazard['side']}这个{label}方向约{near}{unit}到前沿、{far}{unit}到后沿"
     if carry-far_yards<=15:
      risk+=f"，常态Carry刚过后沿，余量偏小，建议避开{label}方向，或考虑另一条方案"
     else:risk+='，仍需给距离波动留余量'
   elif label in risk or (hazard_kind=='water' and any(word in risk for word in ('水体','水塘','湖','河'))):risk+=f'。这个{label}的近远沿暂时无法与地图轮廓核实'
  return risk
 risk=detail('conservative',unit,risk);arisk=detail('aggressive',aunit,arisk)
 return (f'想保守一点，可以用{c}开球，对着落区{target}打。打到预计落点，下一杆大概还剩{left}{unit}；{risk}。\n'
         f'想进取一点，也可以用{a}，瞄向落区{atarget}，下一杆预计还剩{aleft}{aunit}；{arisk}。\n'
         '您今天更想稳一点，还是积极一点？')

def spoken_text(value,reference_course=False,route_details=None,active_round=False):
 from tee_names import display
 value=display(value).replace('设备位置','定位位置')
 if re.match(r'^第[0-9]+洞，[0-9]+杆洞。',value):
  value=re.sub(r'你自报一号木Carry约[0-9.]+(?:码|米)。$','',value)
 if active_round and value in ('好的。','好。','收到。'):value='放松，按自己的节奏打。'
 value=value.replace('最有把握的一支长铁杆','最有把握的铁木杆或长铁杆')
 value=re.sub(r'(?<!铁木杆或)长铁杆','铁木杆或长铁杆',value)
 value=natural_tee_options(value,route_details)
 for sentence in OMIT:value=value.replace(sentence,'')
 replacements={
  '按球道球位考虑。':'',
  '这比你的7铁常态Carry更远，不建议靠额外发力硬补；可比较更长且熟悉的杆与分段过渡。':'建议用熟悉的球杆分段推进，别靠额外发力硬攻。',
  '这比7铁常态Carry短，不默认用7铁全挥；优先比较你熟悉的短杆或控制距离打法。':'建议用熟悉的短杆控制距离。',
  '7铁可以作为攻果岭的候选，先考虑果岭中央这一参考目标，不盲目追旗。':'可考虑7铁，目标取果岭中央，不追旗。',
  '这种球位会增加触球和距离的不确定性，先保证脱困，不承诺按球道Carry飞越障碍。':'先保证脱困，别勉强飞越障碍。',
  '地图缺少完整障碍范围，暂不能确认左右或前后的安全余量。':'障碍范围还需现场确认。',
  '你常见偏右，选目标时要为这个偏差留空间，不只靠反向瞄准抵消。':'给右侧失误留余量。',
  '你常见偏左，选目标时要为这个偏差留空间，不只靠反向瞄准抵消。':'给左侧失误留余量。',
  '你准备采用什么球杆和目标？':'',
 }
 for old,new in replacements.items():value=value.replace(old,new)
 value=re.sub(r'按当前GPS与地图区域，球位判断为(?:球道|长草|沙坑|果岭|发球台)；若现场不同你可以直接更正。','',value)
 value=re.sub(r'你的自报7铁Carry约[0-9.]+(?:码|米)。','',value)
 value=value.replace('水障碍','水域')
 if reference_course:value=value.replace('果岭中心','果岭参考点')
 return value
