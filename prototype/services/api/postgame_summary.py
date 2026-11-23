"""Read-only round review from confirmed scores; never changes coach consent."""
import re
from round_state import fact_value

def requested(text):
 clean=re.sub(r'[\s，,。！!？?]','',text)
 if re.search(r'不想|不需要|不用|不要|先不|暂不|别',clean):return False
 return bool(re.search(r'分析|总结|复盘|回顾',clean) and re.search(r'这场|本场|今天|整场|球局|成绩|打得|打的',clean)) or clean in ('分析','总结','分析总结','总结分析','复盘','回顾','分析一下','总结一下','分析总结一下','复盘一下','回顾一下','做个总结','做个分析','赛后分析','赛后总结')

def detailed_review(state):
 from round_view import summary
 rows=summary(state)['scores']
 if not rows:return '本场还没有已确认的每洞成绩，暂时无法汇总总杆、推杆和罚杆。可以先补记成绩，再做分析。'
 def aggregate(items):
  if not items:return '尚未记分'
  values=[]
  for key,label in [('total','杆'),('putts','推'),('penalties','罚杆')]:
   known=[r[key] for r in items if type(r[key]) is int]
   if not known:values.append(label+'未报');continue
   note=f'（{len(items)-len(known)}洞未报）' if len(known)<len(items) else ''
   values.append(str(sum(known))+label+note)
  return '、'.join(values)
 lines=[f'本场已确认{len(rows)}/18洞，'+aggregate(rows)+'。总杆已含罚杆。']
 for label,low,high in [('前九',1,9),('后九',10,18)]:
  part=[r for r in rows if low<=r['hole']<=high]
  lines.append(f'{label}（已记{len(part)}/9洞）：'+aggregate(part)+'。')
 from course_history_comparison import compare as history_comparison
 lines.append(history_comparison(state)['text'])
 from round_analysis import describe
 lines.append(describe(state))
 snapshot=state.get('evidence',{}).get(fact_value(state,'context.course_snapshot'),{}).get('data',{})
 pars={h['number']:h['par'] for h in snapshot.get('holes',[])}
 relative=[(r,r['total']-pars[r['hole']]) for r in rows if r['hole'] in pars]
 if relative:
  best=min(delta for _,delta in relative)
  holes='、'.join(str(r['hole']) for r,delta in relative if delta==best)
  result='平标准杆' if best==0 else f'低于标准杆{-best}杆' if best<0 else f'高于标准杆{best}杆'
  lines.append(f'已记洞中相对标准杆最好的是第{holes}洞，{result}。')
 threes=[r for r in rows if type(r['putts']) is int and r['putts']>=3]
 penalty=[r for r in rows if type(r['penalties']) is int and r['penalties']>0]
 if penalty:lines.append('复盘优先看罚杆：第'+'、'.join(str(r['hole']) for r in penalty)+'洞有罚杆，结合当时球位和路线选择逐洞回看。')
 if threes:lines.append('推杆重点：第'+'、'.join(str(r['hole']) for r in threes)+'洞出现三推或更多，优先回看第一推距离与停球位置。')
 if not penalty and not threes:lines.append('已报数据中没有罚杆或三推记录；可以选择一洞，结合实际用杆和落点继续复盘。')
 if len(rows)<18:lines.append('尚未记分的球洞未计入，以上是已确认部分的分析。')
 return '\n'.join(lines)


def focus(state):
 from round_view import summary
 rows=summary(state)['scores']
 threes=[r for r in rows if type(r['putts']) is int and r['putts']>=3]
 penalties=[r for r in rows if type(r['penalties']) is int and r['penalties']>0]
 extra_putts=sum(r['putts']-2 for r in threes)
 penalty_count=sum(r['penalties'] for r in penalties)
 if threes and extra_putts>=penalty_count:
  return dict(kind='putting',holes=[r['hole'] for r in threes],finding=f'已记部分有{len(threes)}洞出现三推或更多，最值得先复盘这些洞的推杆过程。',action='下场先关注第一推后的停球距离，再判断问题出在哪里。')
 if penalties:
  holes='、'.join(str(r['hole']) for r in penalties)
  return dict(kind='penalty',holes=[r['hole'] for r in penalties],finding=f'第{holes}洞有罚杆，最值得先回看这些洞的球位和路线选择。',action='下场到这些洞时，先结合当前球位核对落区和障碍余量，再定用杆。')
 return dict(kind='review',holes=[],finding='可以先挑一洞，结合实际用杆和落点回看过程。',action='下场继续记录实际落点，逐步找出更适合自己的球杆和路线。')

def review(state):
 from round_view import summary
 rows=summary(state)['scores']
 if not rows:return '本场还没有已确认的每洞成绩，可以先补记成绩，再一起复盘。'
 total=sum(r['total'] for r in rows)
 lines=[f'今天{total}杆。' if len(rows)==18 else f'目前确认{len(rows)}洞，共{total}杆；以下只看已记部分。']
 from course_history_comparison import compare
 historical=compare(state)
 if historical['status']=='compared':
  def difference(value):
   delta=total-value
   return '持平' if delta==0 else f'少{abs(delta):g}杆' if delta<0 else f'多{delta:g}杆'
  lines.append(f'比本球场同Tee历史最好{difference(historical["best"])}，比历史平均{difference(historical["average"])}。')
 elif historical['status']=='first_record':lines.append('这是首次记录本球场。')
 snapshot=state.get('evidence',{}).get(fact_value(state,'context.course_snapshot'),{}).get('data',{})
 pars={h['number']:h['par'] for h in snapshot.get('holes',[])}
 matched=[(r,r['total']-pars[r['hole']]) for r in rows if r['hole'] in pars]
 if matched:
  best=min(delta for _,delta in matched)
  best_holes=[r['hole'] for r,delta in matched if delta==best]
  names='、'.join(map(str,best_holes[:2]))+('等' if len(best_holes)>2 else '')
  if best<0:
   word=('各抓一只鸟' if len(best_holes)>1 else '抓到小鸟') if best==-1 else '打出老鹰' if best==-2 else '打出低于标准杆'+str(-best)+'杆的成绩'
   lines.append(f'第{names}洞{word}，是本场亮点。')
  elif best==0:lines.append(f'第{names}洞打出Par，值得记住。')
 if all(any(r['hole']==i for r in rows) for i in range(1,19)):
  front=sum(r['total'] for r in rows if r['hole']<=9);back=total-front
  lines.append(f'前九{front}杆，后九{back}杆。')
 selected=focus(state)
 lines.extend([selected['finding'],selected['action'],'您需要我给您播报一下详细数据，还是我们一起来复盘一下某一洞？'])
 return ''.join(lines)
