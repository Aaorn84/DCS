"""Layered post-round delivery: brief speech, expandable data, specific followups."""
import re,unicodedata
from round_state import fact_value,canonical
CHOICES=['播报详细数据','复盘某一洞','下场怎么打']
STAGES=('review_offer','feeling','postgame','coach_consent','focus','plan_confirm','idle')

def mark(state,event_id,expanded=False):
 j=state['journey'];j['round_review_requested']=(j.get('round') or {}).get('id');j.pop('postgame_followup',None)
 if expanded:j['round_review_expand_event']=event_id
 if j['stage']=='review_offer':j['stage']='postgame'
 ensure_cache(state,force=True)

def present(state):
 j=state.get('journey',{});r=j.get('round') or {}
 if not r.get('finished') or not r.get('id') or j.get('round_review_requested')!=r['id']:return None
 cached=j.get('round_review_cache')
 if not cached or cached.get('round_id')!=r['id'] or cached.get('score_key')!=score_key(state):cached=build_cache(state)
 return dict(round_id=r['id'],summary=cached['summary'],details=cached['details'],expand_event=j.get('round_review_expand_event'))

def score_key(state):
 # Small scalar inputs only; opening a card does not scan shot ledgers/maps.
 j=state.get('journey',{});eid=fact_value(state,'context.course_snapshot')
 course=state.get('evidence',{}).get(eid,{}).get('data',{})
 return canonical([[(n,*[fact_value(state,f'holes.{n}.{k}') for k in ('total','putts','penalties')]) for n in range(1,19)],eid,[(h['number'],h.get('par')) for h in course.get('holes',[])]])

def build_cache(state):
 from postgame_summary import review,detailed_review
 return dict(round_id=(state['journey'].get('round') or {}).get('id'),score_key=score_key(state),summary=review(state),details=detailed_review(state))

def ensure_cache(state,force=False):
 j=state.get('journey',{});r=j.get('round') or {}
 if not r.get('finished') or not r.get('id') or j.get('round_review_requested')!=r['id']:return
 cached=j.get('round_review_cache')
 if force or not cached or cached.get('round_id')!=r['id'] or cached.get('score_key')!=score_key(state):j['round_review_cache']=build_cache(state)

def hole_review(state,number):
 from hole_recap import review
 return review(state,number)


def named_hole(state,text):
 def parse(value):
  normalized=re.sub(r'[\s，,。！!？?]','',unicodedata.normalize('NFKC',value)).lower()
  return re.fullmatch(r'(?:复盘|回顾|分析|看看)?([a-z])(?:区|场)?(?:#|第)?(1[0-8]|[1-9])(?:号)?洞?(?:复盘)?',normalized)
 requested=parse(text)
 if not requested:return None
 area,local=requested[1],int(requested[2]);name=area.upper()+str(local)
 snapshot=state.get('evidence',{}).get(fact_value(state,'context.course_snapshot'),{}).get('data',{})
 matches=set()
 for hole in snapshot.get('holes',[]):
  for field in ('source_name','name'):
   value=hole.get(field)
   parsed=parse(value) if isinstance(value,str) else None
   if parsed and parsed[1]==area and int(parsed[2])==local:matches.add(hole['number'])
 return dict(label=name,number=next(iter(matches)) if len(matches)==1 else None,ambiguous=len(matches)>1)

def handle(state,text,event_id):
 j=state.get('journey',{});r=j.get('round') or {}
 if j.get('stage') not in STAGES or not r.get('finished'):return None
 clean=re.sub(r'[\s，,。！!？?]','',text)
 def result(words):return dict(text=words,choices=CHOICES)
 if clean in ('详细数据','播报','播报一下','播报详细数据','播报一下详细数据','听详细数据','听一下详细数据','读一下详细数据','详细播报','我要听详细数据','先播报详细数据') or (re.search(r'(?:播报|读|听).*(?:详细数据|详细统计)',clean) and not re.search(r'不想|不用|不要|先不',clean)):
  from postgame_summary import detailed_review
  mark(state,event_id,True);return result(state['journey']['round_review_cache']['details'])
 if clean in ('看详细数据','详细数据','查看详细数据','展开详细数据','详细分析','详细总结') or (re.search(r'详细.*(?:数据|统计|分析|总结|复盘)',clean) and not re.search(r'不想|不用|不要|先不',clean)):
  mark(state,event_id,True);return result('详细数据已展开在“本场记录”中，可以查看成绩分布、洞型表现和技术统计。')
 if clean in ('复盘某一洞','复盘一洞','逐洞复盘','一起复盘某一洞','我们一起来复盘一下某一洞') or (j.get('round_review_requested')==r['id'] and clean in ('复盘','复盘一下','一起复盘','我们复盘一下')):
  j['postgame_followup']='hole';return result('想复盘哪一洞？可以说“第3洞”，也可以报本场路线中的分区洞号，例如“A5”。')
 alias=named_hole(state,text)
 if alias:
  if alias['number'] is not None:
   j.pop('postgame_followup',None);return result(alias['label']+' · '+hole_review(state,alias['number']))
  j['postgame_followup']='hole'
  return result(('本场路线中有多个' if alias['ambiguous'] else '本场路线中未找到')+alias['label']+'，请用“第几洞”指定本场洞号。')
 token=r'([1-9]|1[0-8]|[一二两三四五六七八九十]{1,3})'
 match=re.fullmatch(r'(?:复盘|回顾|分析|看看)?第?'+token+r'(?:号)?洞(?:复盘)?',clean)
 if not match and j.get('postgame_followup')=='hole':match=re.fullmatch(token,clean)
 if match:
  labels=['一','二','三','四','五','六','七','八','九','十','十一','十二','十三','十四','十五','十六','十七','十八']
  numbers={label:i+1 for i,label in enumerate(labels)};numbers['两']=2
  number=int(match[1]) if match[1].isdigit() else numbers.get(match[1])
  if number:
   j.pop('postgame_followup',None);return result(hole_review(state,number))
 if clean in ('下场怎么打','下一场怎么打','下次怎么打','下场建议'):
  from postgame_summary import focus
  j.pop('postgame_followup',None)
  f=focus(state);return result('下一场先盯一个重点：'+f['action']+'到具体球洞后，再按当天的Tee、旗位和实际球位确认方案。')
 from postgame_summary import requested,review
 if requested(text) or (j['stage']=='review_offer' and clean in ('需要','要','好的','好','可以','是','来一个','需要总结')):
  mark(state,event_id);return result(state['journey']['round_review_cache']['summary'])
 return None
