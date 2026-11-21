"""Read-only sequence numbering and relief-origin consistency checks."""
from shot_evidence import haversine

def counted(flow):
 from ball_rules import ball_counts
 number=0;shots=[]
 for index,item in enumerate(flow.get('sequence',[])):
  if not item.get('active',True) or item.get('ball_id') not in flow.get('balls',{}) or not ball_counts(flow,item['ball_id']):continue
  if item['kind']=='penalty':number+=item['amount']
  elif item['kind']=='stroke':
   number+=1;shots.append(dict(item,stroke_number=number,sequence_index=index))
 return shots

def replay_origin_conflicts(flow):
 shots=counted(flow);by_id={r['id']:r for r in shots};conflicts={}
 for incident in flow.get('incidents',[]):
  if incident.get('status')=='cancelled' or incident.get('phase')!='closed' or incident.get('option')!='stroke_distance' or incident.get('promoted'):continue
  expected=incident.get('origin');original=by_id.get(incident.get('shot_id'))
  if not expected or not original:continue
  completed=incident.get('completed_sequence_count')
  after=completed if type(completed) is int and 0<=completed<=len(flow.get('sequence',[])) else original['sequence_index']+1
  replay=next((r for r in shots if r['sequence_index']>=after),None)
  if not replay or not replay.get('origin'):continue
  tolerance=max(10,expected.get('accuracy_m',0)+replay['origin'].get('accuracy_m',0))
  if haversine(expected,replay['origin'])>tolerance:
   conflicts[replay['id']]=dict(stroke_number=replay['stroke_number'],incident_id=incident['id'],reason='回原位重打的处理记录与这一杆保存的起点不一致')
 return conflicts
