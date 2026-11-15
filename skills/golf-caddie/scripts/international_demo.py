#!/usr/bin/env python3
"""Offline multilingual semantic flow. No overseas course, ASR or translation claim."""
import argparse,json
from round_state import Engine,fact_value
from international import LOCALES, snapshot

def run_demo(locale='en-US',emit=print):
 e=Engine(':memory:','international-demo');e.create('demo');n=0;steps=[]
 def send(kind='semantic',**v):
  nonlocal n
  n+=1;p=dict(protocol_version=4,event_id='demo-'+str(n),observed_at='2026-11-08T00:00:00Z',type=kind,**v)
  r=e.command('demo',str(n),'international_event',p,now=1794096000)
  steps.append({'input':v,'stage':snapshot(e.state('demo'))['journey']['stage'],'status':r.get('status'),'reply':r['text'],'spoken':r['speak_allowed']})
 def semantic(kind,**slots):send(candidate=dict(type=kind,slots=slots))
 try:
  send('configure',configuration={'locale':locale,'market_region':'US','distance_unit':'yd','timezone':'America/New_York'})
  semantic('state_transition',action='skip_onboarding')
  semantic('profile_answer',course='synthetic-demo');semantic('profile_answer',tee='blue');semantic('profile_answer',number=1)
  semantic('player_intent',approach='conservative');semantic('state_transition',action='start')
  samples={'en-US':'How far?','en-GB':'How far is it?','ja-JP':'残り距離は？','ko-KR':'얼마 남았어?','es-ES':'¿Cuánto falta?','pt-PT':'Quanto falta?','de-DE':'Wie weit ist es noch?','fr-FR':'Quelle distance reste-t-il ?','it-IT':'Quanto manca?'}
  if locale in samples:send('utterance',text=samples[locale])
  else:semantic('fact_request',domain='distance')
  semantic('execution_report',club='7i');semantic('score_report',total=6,putts=2,penalties=0);semantic('confirmation',action='score')
  semantic('interaction_override',coaching=False);semantic('state_transition',action='finish');semantic('state_transition',action='finish_confirm')
  result={'locale':locale,'steps':steps,'confirmed_total':fact_value(e.state('demo'),'holes.1.total'),'replay_matches':e.state('demo')==e.replay('demo'),'capabilities':snapshot(e.state('demo'))['capabilities']}
  if emit:emit(json.dumps(result,ensure_ascii=False,indent=2))
  return result
 finally:e.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--locale',choices=LOCALES,default='en-US');run_demo(p.parse_args().locale)
