"""Explainable preference learning from explicit trade-offs, not personality labels.
Safety and current instructions always precede learned preferences.
"""
VERSION=1
MIN_ROUNDS=3
MIN_CHOICES=6

def preference(journey):
 if journey.get('memory_allowed') is not True:return 'unconfirmed'
 samples=[v for v in journey.get('tee_preference_samples',[]) if v.get('hole') is not None]
 rounds=list(dict.fromkeys(v['round'] for v in reversed(samples)))[:5]
 samples=[v for v in samples if v['round'] in rounds]
 if len(rounds)<MIN_ROUNDS or len(samples)<MIN_CHOICES:return 'unconfirmed'
 distance=sum(v['choice']=='distance' for v in samples)/len(samples)
 return 'distance' if distance>=.7 else 'control' if distance<=.3 else 'balanced'

def record(state,offer,decisions):
 j=state['journey']
 if j.get('memory_allowed') is not True:return
 options=offer.get('options',[])
 if len(options)<2:return
 carries=[o.get('carry_yards') for o in options]
 if any(type(v) not in (int,float) for v in carries) or max(carries)-min(carries)<15:return
 samples=j.setdefault('tee_preference_samples',[]);rid=(j.get('round') or {}).get('id')
 if not rid:return
 for d in decisions:
  if d.get('source')!='user_report' or not d.get('event_id'):continue
  matched=[o for o in options if o.get('club')==d.get('club')]
  if len(matched)!=1:continue
  if any(v['event']==d['event_id'] for v in samples):continue
  # A club choice is preference evidence, not proof of a completed or good shot.
  selected=matched[0]
  longer=[o for o in options if o['carry_yards']>selected['carry_yards']]
  shorter=[o for o in options if o['carry_yards']<selected['carry_yards']]
  # Only genuine, evidenced distance-versus-risk trade-offs teach style.
  risk=selected.get('risk_factors')
  peers=shorter if selected['carry_yards']==max(carries) else longer
  if risk is None or not peers or any(o.get('risk_factors') is None for o in peers):continue
  if selected['carry_yards']==max(carries):
   if not any(all(x<=y for x,y in zip(o['risk_factors'],risk)) and o['risk_factors']!=risk for o in peers):continue
   choice='distance'
  else:
   if not any(all(x<=y for x,y in zip(risk,o['risk_factors'])) and risk!=o['risk_factors'] for o in peers):continue
   choice='control'
  hole=d.get('hole')
  if hole is None:continue
  samples[:]=[v for v in samples if not (v['round']==rid and v.get('hole')==hole)]
  samples.append(dict(round=rid,hole=hole,event=d['event_id'],choice=choice,source='explicit_tee_choice'))
 del samples[:-60]
 j['tee_style_summary']=dict(version=VERSION,preference=preference(j),samples=len(samples),basis='explicit_choices_not_ability',override_allowed=True)
