"""Read-only score and stroke presentation from the shared core projection."""
from round_state import fact_value
def summary(s):
    rows=[]
    for i in range(1,19):
        total=fact_value(s,f'holes.{i}.total')
        if total is not None:rows.append({'hole':i,'total':total,'putts':fact_value(s,f'holes.{i}.putts'),'penalties':fact_value(s,f'holes.{i}.penalties')})
    known=[r['putts'] for r in rows if r['putts'] is not None]
    return {'confirmed_holes':len(rows),'confirmed_subtotal':sum(r['total'] for r in rows) if rows else None,
            'putt_opportunities':len(known),'three_putts':sum(n>=3 for n in known),'scores':rows}
def compare(plan,current):
    base=plan['baseline']
    if plan['focus']!='减少三推' or min(base['putt_opportunities'],current['putt_opportunities'])<6:
        return {'decision':'evidence_insufficient','text':'可比较的证据还不够，先保留原重点，不宣称改善。'}
    b=base['three_putts']/base['putt_opportunities'];n=current['three_putts']/current['putt_opportunities']
    return {'decision':'consolidate' if n<b else 'adjust_practice','text':'本场三推比例较低，先巩固；尚不能认定稳定改善。' if n<b else '暂未看到三推比例下降，保留重点，调整练习后继续观察。'}

def round_records(s):
 j=s.get('journey',{});rid=(j.get('round') or {}).get('id');clubs=[]
 from projected_ledger import rows
 for flow in j.get('round_ledger',{}).values():
  if flow['scope'][0]==rid:clubs.extend(rows(flow))
 model=j.get('offline_local_round') or {};draft=model.get('draft')
 if draft:draft={key:draft.get(key) for key in ('hole','total','putts','penalties','awaiting')}
 return dict(clubs=sorted(clubs,key=lambda r:(r['hole'],r['stroke_number'])),hole_pars={h['number']:h['par'] for h in s.get('evidence',{}).get(fact_value(s,'context.course_snapshot'),{}).get('data',{}).get('holes',[])},score_draft=draft)

def view(s):
 from application_questions import QUESTIONS
 from history_access import page
 from postgame_delivery import present,CHOICES
 j=s.get('journey',{});stage=j.get('stage','memory');q,choices=QUESTIONS.get(stage,('',[]));r=j.get('round') or {};navigation={}
 if r.get('course')=='dongguan-phoenix-ab-blue-demo':
  from phoenix_demo import preview
  navigation=dict(course_name='东莞凤凰山 A+B蓝Tee（来源坐标演示）',simulation=preview(fact_value(s,'context.active_hole') or r.get('start_hole',1),s.get('evidence',{}).get(fact_value(s,'context.course_snapshot'),{}).get('data')))
  pos=s.get('facts',{}).get('context.device_position',{})
  navigation['simulation']['device_position']=pos.get('value') if pos.get('valid') else None
  if stage=='tee':choices=['蓝台']
  if stage=='start_hole':choices=[str(n) for n in range(1,19)]
 review=present(s)
 if review and stage=='postgame':choices=list(CHOICES)
 history=page(s)
 return dict(navigation,stage=stage,profile=j.get('profile',{}),memory_allowed=j.get('memory_allowed'),shot_audio=j.get('shot_audio',{}),round=j.get('round'),history=history['rounds'],history_count=history['total'],history_has_more=history['has_more'],coach=j.get('coach',{'enabled':False}),choices=['继续'] if j.get('quiet') else choices,question=q,version=s['version'],round_review=review,score_summary=summary(s),round_records=round_records(s),quiet=j.get('quiet',False),tee_dispersion=j.get('tee_dispersion_summary',{}),current_hole=fact_value(s,'context.active_hole'),carry_estimates=[],distance_unit=j.get('profile',{}).get('units',{}).get('value','码'))
