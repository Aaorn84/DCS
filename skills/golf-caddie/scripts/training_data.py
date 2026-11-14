#!/usr/bin/env python3
"""Provider-neutral, review-gated multilingual dataset tooling. Does not train a model."""
import argparse,copy,hashlib,json,re
from pathlib import Path
from international import EVENT_TYPES,LOCALES,club

SCHEMA_VERSION=1
SPLITS=('train','validation','test')

def require(ok,message):
 if not ok:raise ValueError(message)

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def assigned_split(family):
 n=int(hashlib.sha256(family.encode()).hexdigest()[:8],16)%10
 return 'train' if n<8 else 'validation' if n==8 else 'test'

def fingerprint(case,locale):
 variant=case['variants'][locale]
 return digest({'case_id':case['case_id'],'family_id':case['family_id'],'provenance':case['provenance'],
   'context':variant['context'],'utterance':variant['utterance'],'suggested_reply':variant['suggested_reply'],
   'locale':locale,'semantic_target':case['semantic_target'],'expected_state':case['expected_state'],
   'expected_action':case['expected_action'],'reply_constraints':case['reply_constraints']})

def validate(case):
 require(isinstance(case,dict),'case must be an object')
 keys={'schema_version','case_id','family_id','split','provenance','semantic_target','expected_state','expected_action','reply_constraints','variants'}
 require(set(case)==keys,'unknown or missing case fields')
 require(type(case['schema_version']) is int and case['schema_version']==SCHEMA_VERSION,'unsupported dataset schema')
 for k in ('case_id','family_id'):require(isinstance(case[k],str) and re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,99}',case[k]),'invalid '+k)
 require(case['split']==assigned_split(case['family_id']),'split must be derived from family_id')
 p=case['provenance'];require(isinstance(p,dict) and set(p)=={'kind','training_permission','privacy_status','consent_reference','deidentification_reference'},'invalid provenance')
 require(p['kind'] in ('synthetic','consented_user'),'invalid provenance kind')
 require(p['training_permission'] in ('granted','not_granted','withdrawn'),'invalid training permission')
 require(p['privacy_status'] in ('no_personal_data','deidentified_reviewed','pending'),'invalid privacy status')
 if p['kind']=='consented_user':
  require(p['privacy_status']!='no_personal_data','user data needs explicit deidentification review')
  if p['training_permission']=='granted':require(isinstance(p['consent_reference'],str) and bool(p['consent_reference'].strip()),'user data needs a training-consent reference')
  if p['privacy_status']=='deidentified_reviewed':require(isinstance(p['deidentification_reference'],str) and bool(p['deidentification_reference'].strip()),'user data needs a deidentification-review reference')
 target=case['semantic_target'];require(isinstance(target,dict) and set(target)=={'type','slots'},'invalid semantic target')
 require(target['type'] in EVENT_TYPES and isinstance(target['slots'],dict),'invalid semantic taxonomy')
 slots=target['slots']
 if 'club' in slots:club(slots['club'])
 if target['type']=='correction' and slots.get('field') in ('actual_club','planned_club'):club(slots.get('value'))
 for field in ('total','putts','penalties'):
  if field in slots:require(type(slots[field]) is int and (1 if field=='total' else 0)<=slots[field]<=30,'invalid score slot')
 require(isinstance(case['expected_state'],list) and bool(case['expected_state']),'state expectations required')
 for item in case['expected_state']:
  require(isinstance(item,dict) and set(item)=={'path','op','value'},'invalid state assertion')
  require(isinstance(item['path'],str) and bool(re.fullmatch(r'[a-zA-Z0-9_.\[\]-]+',item['path'])),'invalid state path')
  require(item['op'] in ('equals','unchanged','unknown','not_created'),'unsupported assertion operator')
 action=case['expected_action'];require(isinstance(action,dict) and set(action)=={'kind','max_questions'},'invalid expected action')
 require(action['kind'] in ('answer','clarify','record_candidate','request_confirmation','commit','defer','no_state_change'),'invalid action')
 require(type(action['max_questions']) is int and action['max_questions'] in (0,1),'at most one question')
 require(isinstance(case['reply_constraints'],list) and bool(case['reply_constraints']) and all(isinstance(x,str) and x for x in case['reply_constraints']),'reply constraints required')
 require(isinstance(case['variants'],dict) and 'zh-CN' in case['variants'] and not set(case['variants'])-set(LOCALES),'Chinese reference and supported locales required')
 for locale,v in case['variants'].items():
  require(isinstance(v,dict) and set(v)=={'context','utterance','suggested_reply','translation_of','review'},'invalid variant')
  require(v['translation_of']==(None if locale=='zh-CN' else 'zh-CN'),'invalid translation lineage')
  require(isinstance(v['context'],list),'context must be a list')
  for msg in v['context']:
   require(isinstance(msg,dict) and set(msg)=={'role','content'} and msg['role'] in ('user','assistant','system') and isinstance(msg['content'],str),'invalid dialogue context')
  for key in ('utterance','suggested_reply'):require(isinstance(v[key],str) and 0<len(v[key])<=10000,'invalid '+key)
  review=v['review'];require(isinstance(review,dict) and set(review)=={'domain','language'},'two review dimensions required')
  for dimension,entry in review.items():
   require(isinstance(entry,dict) and set(entry)=={'status','reviewer','content_sha256'},'invalid review entry')
   require(entry['status'] in ('pending','approved','rejected'),'invalid review status')
   if entry['status']=='approved':
    require(isinstance(entry['reviewer'],str) and bool(entry['reviewer'].strip()),'approved review needs reviewer')
    require(entry['content_sha256']==fingerprint(case,locale),'review is stale: content changed')
 return case

def load(path):
 cases=[];ids=set()
 for n,line in enumerate(Path(path).read_text().splitlines(),1):
  if not line.strip():continue
  try:c=validate(json.loads(line))
  except (ValueError,KeyError,TypeError) as exc:raise ValueError(f'line {n}: {exc}') from exc
  require(c['case_id'] not in ids,'duplicate case id');ids.add(c['case_id']);cases.append(c)
 require(bool(cases),'empty dataset')
 # All cases with the same family have one split, including future paraphrases.
 families={}
 for c in cases:
  require(families.setdefault(c['family_id'],c['split'])==c['split'],'family leakage')
 return cases

def eligible(c,locale):
 p=c['provenance']
 return (p['training_permission']=='granted' and p['privacy_status'] in ('no_personal_data','deidentified_reviewed')
         and locale in c['variants'] and all(e['status']=='approved' and e['content_sha256']==fingerprint(c,locale) for e in c['variants'][locale]['review'].values()))

def report(cases):
 return {'schema_version':SCHEMA_VERSION,'cases':len(cases),'families':len({c['family_id'] for c in cases}),
  'splits':{s:sum(c['split']==s for c in cases) for s in SPLITS},
  'locales':{l:{'variants':sum(l in c['variants'] for c in cases),'eligible':sum(eligible(c,l) for c in cases)} for l in LOCALES},
  'model_training_started':False,'note':'Draft translations are not native-language approval. No real-user logs are collected.'}

def export_records(cases,locales,purpose='train',split='train'):
 require(purpose in ('train','eval') and split in SPLITS,'invalid export purpose/split')
 require(purpose!='train' or split=='train','validation/test families cannot enter training')
 require(bool(locales) and not set(locales)-set(LOCALES),'unsupported export locale')
 records=[]
 for c in cases:
  validate(c)
  if c['split']!=split:continue
  for locale in dict.fromkeys(locales):
   if not eligible(c,locale):continue
   v=c['variants'][locale]
   prompt={'locale':locale,'context':v['context'],'utterance':v['utterance']}
   target={'candidate':c['semantic_target'],'action':c['expected_action'],'reply_constraints':c['reply_constraints']}
   row={'id':c['case_id']+':'+locale,'family_id':c['family_id'],'locale':locale,'content_sha256':fingerprint(c,locale)}
   if purpose=='train':row['messages']=[{'role':'system','content':'Interpret golf dialogue as a candidate event. Do not write state or infer missing facts. Return JSON.'},{'role':'user','content':canonical(prompt)},{'role':'assistant','content':canonical(target)}]
   else:row.update(input=prompt,expected=target,expected_state=c['expected_state'],reference_reply=v['suggested_reply'])
   records.append(row)
 return records

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['validate','report','fingerprint','export']);parser.add_argument('dataset');parser.add_argument('--case');parser.add_argument('--locale',action='append');parser.add_argument('--purpose',choices=['train','eval'],default='train');parser.add_argument('--split',choices=SPLITS,default='train');parser.add_argument('--output');args=parser.parse_args()
 try:
  cases=load(args.dataset)
  if args.action in ('validate','report'):out=report(cases)
  elif args.action=='fingerprint':
   require(args.case is not None and args.locale is not None and len(args.locale)==1,'case and one locale required')
   selected=[c for c in cases if c['case_id']==args.case];require(len(selected)==1 and args.locale[0] in selected[0]['variants'],'case/locale not found');out={'content_sha256':fingerprint(selected[0],args.locale[0])}
  else:
   require(args.output is not None,'output path required')
   records=export_records(cases,args.locale or ['zh-CN'],args.purpose,args.split)
   require(bool(records),'no reviewed and consent-eligible records; export blocked')
   output=Path(args.output);manifest=output.with_suffix(output.suffix+'.manifest.json')
   require(not output.exists() and not manifest.exists(),'output already exists')
   data=''.join(canonical(r)+'\n' for r in records)
   out={'schema_version':1,'purpose':args.purpose,'split':args.split,'record_count':len(records),'families':sorted({r['family_id'] for r in records}),'sha256':hashlib.sha256(data.encode()).hexdigest(),'dataset_sha256':hashlib.sha256(Path(args.dataset).read_bytes()).hexdigest()}
   with output.open('x') as f:f.write(data)
   with manifest.open('x') as f:f.write(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except (ValueError,OSError,KeyError,TypeError) as exc:print(json.dumps({'error':str(exc)},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
