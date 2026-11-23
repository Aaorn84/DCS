"""Cross-runtime test driver, not a network service."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/api'))
from shared_core import create_local_round,apply_local_command,totals,CORE_VERSION
from round_state import StateError
pack=dict(schema=1,core_version=CORE_VERSION,round=dict(id='r',tee='蓝Tee',start_hole=1),course=dict(course_id='c',holes=[dict(number=i,par=4) for i in range(1,19)]))
if __name__=='__main__':
 results=[]
 for case in json.load(sys.stdin):
  s=create_local_round(pack);states=[]
  for i,step in enumerate(case['steps']):
   e=dict(v=1,semantics=2,id='e'+str(i),at='2026-11-22T01:00:00+00:00',expected_revision=s['revision'],command=step['command'],data=step.get('data',{}))
   if 'semantics' in step:e['semantics']=step['semantics']
   try:s=apply_local_command(s,e);states.append(dict(state=s,totals=totals(s),error=False))
   except StateError as exc:states.append(dict(state=s,totals=totals(s),error=True,message=str(exc)))
  results.append(states)
 json.dump(results,sys.stdout,ensure_ascii=False)
