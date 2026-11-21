"""Scorecard analysis with explicit coverage; no invented shot metrics or SG."""
from round_state import fact_value

def analyze(state):
 from journey import summary
 rows=summary(state)['scores']
 snapshot=state.get('evidence',{}).get(fact_value(state,'context.course_snapshot'),{}).get('data',{})
 pars={h['number']:h['par'] for h in snapshot.get('holes',[]) if h.get('par') in (3,4,5)}
 matched=[r for r in rows if r['hole'] in pars]
 buckets=dict(albatross_or_better=0,eagle=0,birdie=0,par=0,bogey=0,double_bogey_plus=0)
 types=[]
 for row in matched:
  delta=row['total']-pars[row['hole']]
  key='albatross_or_better' if delta<=-3 else {-2:'eagle',-1:'birdie',0:'par',1:'bogey'}.get(delta,'double_bogey_plus')
  buckets[key]+=1
 for par in (3,4,5):
  group=[r for r in matched if pars[r['hole']]==par]
  types.append(dict(par=par,holes=len(group),average=sum(r['total'] for r in group)/len(group) if group else None,to_par=sum(r['total']-par for r in group)))
 putts=[r['putts'] for r in rows if type(r['putts']) is int]
 from round_technical_stats import calculate
 technical=calculate(state,rows,pars)
 return dict(confirmed_holes=len(rows),par_coverage=len(matched),par_total=sum(pars[r['hole']] for r in matched) if matched else None,to_par=sum(r['total']-pars[r['hole']] for r in matched) if matched else None,
             distribution=buckets,hole_types=types,putting=dict(known_holes=len(putts),total=sum(putts) if putts else None,average=sum(putts)/len(putts) if putts else None,three_putt_holes=sum(v>=3 for v in putts)),
             technical=technical)

def describe(state):
 a=analyze(state);lines=[]
 if not a['confirmed_holes']:return ''
 if a['to_par'] is not None:
  delta=a['to_par'];word='平标准杆' if delta==0 else f'高于标准杆{delta}杆' if delta>0 else f'低于标准杆{-delta}杆'
  lines.append(f'相对标准杆：{word}（当前球场数据中这{a["par_coverage"]}洞标准杆合计{a["par_total"]}杆）。')
 if a['par_coverage']:
  labels=dict(albatross_or_better='信天翁及更好',eagle='老鹰',birdie='小鸟',par='标准杆',bogey='柏忌',double_bogey_plus='双柏忌及以上')
  lines.append('得分分布：'+'、'.join(f'{labels[k]}{v}洞' for k,v in a['distribution'].items() if k!='albatross_or_better' or v)+'。')
  groups=[f'{v["par"]}杆洞平均{v["average"]:.2f}杆（{v["holes"]}洞）' for v in a['hole_types'] if v['holes']]
  lines.append('洞型表现：'+'；'.join(groups)+'。')
 if a['putting']['average'] is not None:
  p=a['putting'];lines.append(f'平均每洞{p["average"]:.2f}推（已报{p["known_holes"]}洞），其中三推及以上{p["three_putt_holes"]}洞。')
 from round_technical_stats import describe as technical_description
 lines.append(technical_description(a['technical']))
 return '\n'.join(lines)
