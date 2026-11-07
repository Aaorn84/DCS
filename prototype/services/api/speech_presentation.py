"""User-facing copy policy; does not mutate evidence, decisions or replay journals."""
import re
OMIT=(
 '风、滚动和个人散布尚未计入，仍要留余量。',
 '风、滚动和个人散布未计入，落区宽度不能替代命中概率；未标障碍也不证明无障碍。',
 '风、高差、滚动和实际散布尚未计入；果岭中央也不等于已验证安全区。',
)
def spoken_text(value,reference_course=False):
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
 if reference_course:value=value.replace('果岭中心','果岭参考点')
 return value
