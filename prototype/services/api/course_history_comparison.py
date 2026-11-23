"""Compare complete recorded rounds at the same course and tee, excluding self."""
from round_state import fact_value
from collections.abc import Mapping
import math

def basis(state):
 data=state.get('evidence',{}).get(fact_value(state,'context.course_snapshot'),{}).get('data',{})
 return {str(h['number']):dict(par=h.get('par'),published_yardage=h.get('published_yardage')) for h in data.get('holes',[])}

def tee(value):
 return value.replace('Tee','台').replace('tee','台').replace('T','台') if isinstance(value,str) else None

def complete_total(scores):
 if len(scores)!=18 or {r.get('hole') for r in scores}!=set(range(1,19)):return None
 if not all(type(r.get('total')) is int and r['total']>0 for r in scores):return None
 return sum(r['total'] for r in scores)

def comparable_basis(value):
 if not isinstance(value,Mapping) or set(value)!={str(n) for n in range(1,19)}:return False
 for row in value.values():
  if not isinstance(row,Mapping) or type(row.get('par')) is not int or not 2<=row['par']<=7:return False
  length=row.get('published_yardage')
  if type(length) not in (int,float) or not math.isfinite(length) or length<=0:return False
 return True

def compare(state):
 from round_view import summary
 j=state.get('journey',{});current=j.get('round') or {};course=current.get('course');rid=current.get('id')
 prepared=j.get('native_history_comparison')
 if prepared is not None:
  if j.get('memory_allowed') is False:return dict(status='memory_disabled',text='当前未开启跨场记忆，本场不使用此前成绩作对比。')
  if not prepared['prior']:return dict(status='first_record',text='本系统暂无此前的本球场成绩，这是首次记录本球场，本场不作历史对比。')
  total=complete_total(summary(state)['scores'])
  if total is None:return dict(status='incomplete_current',text='本场尚无完整18洞确认成绩，暂不比较整场最好成绩和平均成绩。')
  if not prepared['count']:return dict(status='no_comparable_rounds',text='已有本球场历史记录，但没有同Tee、可比球场数据的完整18洞成绩，本场不作总杆对比。')
  return describe(total,prepared['best'],prepared['sum']/prepared['count'],prepared['count'])
 prior={}
 for entry in j.get('history',[]):
  old=entry.get('round',{});old_id=old.get('id')
  if not old_id or old_id==rid or old.get('course')!=course or old.get('finished') is not True:continue
  prior[old_id]=entry
 if not prior:return dict(status='first_record',text='本系统暂无此前的本球场成绩，这是首次记录本球场，本场不作历史对比。')
 if j.get('memory_allowed') is False:return dict(status='memory_disabled',text='当前未开启跨场记忆，本场不使用此前成绩作对比。')
 current_total=complete_total(summary(state)['scores'])
 if current_total is None:return dict(status='incomplete_current',text='已有本球场历史成绩；本场尚无完整18洞确认成绩，暂不比较整场最好成绩和平均成绩。')
 current_basis=basis(state);eligible=[]
 for entry in prior.values():
  old=entry['round'];total=complete_total(entry.get('scores',[]))
  if total is None or not tee(current.get('tee')) or tee(old.get('tee'))!=tee(current.get('tee')):continue
  stored=entry.get('course_basis')
  if not isinstance(stored,list) or len(stored)!=1:continue
  saved_basis=stored[0]
  if not comparable_basis(current_basis) or not comparable_basis(saved_basis) or saved_basis!=current_basis:continue
  eligible.append(total)
 if not eligible:return dict(status='no_comparable_rounds',text='已有本球场历史记录，但没有同Tee、可比球场数据的完整18洞成绩，本场不作总杆对比。')
 best=min(eligible);average=sum(eligible)/len(eligible)
 return describe(current_total,best,average,len(eligible))

def describe(current_total,best,average,count):
 def difference(value):
  delta=current_total-value
  return '持平' if delta==0 else f'少{abs(delta):g}杆' if delta<0 else f'多{delta:g}杆'
 text=(f'同球场同Tee历史对比（此前{count}场完整18洞，不含本场）：'
       f'最好{best}杆，本场{current_total}杆，比最好成绩{difference(best)}；'
       f'平均{average:.1f}杆，本场比历史平均{difference(average)}。')
 return dict(status='compared',rounds=count,best=best,average=average,current=current_total,text=text)
