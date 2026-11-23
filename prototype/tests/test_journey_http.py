from testing.database import TestDatabase
import unittest,tempfile,threading,json,urllib.request,urllib.error
from services.api.server import make_server
class JourneyHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TestDatabase();self.server=make_server(self.tmp.url,port=0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port);self.n=0
  self.token=self.call('/auth/register',{'email':'j@example.test','password':'password-12345'})[1]['token']
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def call(self,path,body,token=None):
  req=urllib.request.Request(self.base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
  try:
   with urllib.request.urlopen(req) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:
   with e:return e.code,json.load(e)
 def msg(self,text):
  self.n+=1;return self.call('/journey',{'action':'core_event','operation_id':'op'+str(self.n),'event':{'type':'message','event_id':'e'+str(self.n),'observed_at':'2026-11-07T00:00:00+08:00','text':text}},self.token)
 def test_requires_authentication(self):self.assertEqual(self.call('/journey',{'action':'snapshot'})[0],401)
 def test_account_isolation(self):
  self.msg('可以记住');other=self.call('/auth/register',{'email':'other@example.test','password':'password-12345'})[1]['token']
  self.assertEqual(self.call('/journey',{'action':'snapshot'},other)[1]['journey']['stage'],'memory')
 def test_reject_body_owner_and_stale_version(self):
  self.assertEqual(self.call('/journey',{'action':'core_event','operation_id':'x','event':{'owner':'other'}},self.token)[0],400)
  self.msg('可以记住')
  self.assertEqual(self.call('/journey',{'action':'core_event','operation_id':'stale','expected_version':0,'event':{'type':'message','event_id':'s','text':'阿明','observed_at':'2026-11-07T00:00:00+08:00'}},self.token)[0],409)
 def test_lost_receipt_after_progress_does_not_repeat_old_question(self):
  body={'action':'core_event','operation_id':'retry','event':{'type':'message','event_id':'retry','observed_at':'2026-11-07T00:00:00+08:00','text':'可以记住'}}
  self.assertEqual(self.call('/journey',body,self.token)[0],200)
  self.msg('阿明')
  code,d=self.call('/journey',body,self.token);self.assertEqual(code,200)
  self.assertEqual(d['result']['text'],'');self.assertFalse(d['result']['speak_allowed']);self.assertEqual(d['journey']['stage'],'proactive')
 def test_default_yards_and_natural_reminder_permission(self):
  self.msg('可以记住')
  body={'action':'core_event','operation_id':'name','event':{'type':'message','event_id':'name','observed_at':'2026-11-07T00:00:00+08:00','text':'测试球友'}}
  code,d=self.call('/journey',body,self.token);self.assertEqual(code,200);self.assertEqual(d['journey']['stage'],'proactive');self.assertEqual(d['journey']['distance_unit'],'码')
  code,d=self.msg('no problem');self.assertEqual(code,200);self.assertTrue(d['journey']['profile']['proactive']['value']);self.assertEqual(d['journey']['stage'],'shot_recording')
  code,d=self.msg('我不习惯使用码，我更习惯用米');self.assertEqual(code,200);self.assertEqual(d['journey']['distance_unit'],'米');self.assertEqual(d['journey']['stage'],'shot_recording')
  self.assertEqual(self.call('/journey',{'action':'snapshot'},self.token)[1],self.call('/journey',{'action':'replay'},self.token)[1])

 def test_history_metadata_is_paged_and_shots_load_only_on_explicit_request(self):
  from services.api.round_state import Engine,canonical
  self.call('/journey',{'action':'snapshot'},self.token);owner=self.server.store.user(self.token)
  e=Engine(self.server.store.path,owner)
  try:
   s=e.state('companion-journey');s['journey']=dict(stage='postgame',round=dict(id='current',course='course',finished=True),profile={},coach={'enabled':False},history=[],quiet=False,memory_allowed=True)
   for i in range(25):s['journey']['history'].append(dict(round=dict(id='old-'+str(i),course='course',finished=True),confirmed_holes=18,confirmed_subtotal=80,scores=[dict(hole=1,total=4,putts=2,penalties=0)],hole_history={'1':dict(signature='s',shots=[dict(id='shot',club='7号铁',stroke_number=1,distance_m=140)])}))
   e.db.execute('UPDATE rounds SET state=%s WHERE owner=%s AND id=%s',(canonical(s),owner,'companion-journey'));e.compact('companion-journey')
  finally:e.close()
  code,d=self.call('/journey',{'action':'snapshot'},self.token);self.assertEqual(code,200);j=d['journey'];self.assertEqual(len(j['history']),20);self.assertEqual(j['history_count'],25);self.assertNotIn('hole_history',j['history'][0]);self.assertNotIn('scores',j['history'][0])
  code,d=self.call('/journey',{'action':'history','offset':20,'limit':20},self.token);self.assertEqual(code,200);self.assertEqual(len(d['history_page']['rounds']),5)
  code,d=self.call('/journey',{'action':'history_hole','round_id':'old-0','hole':1},self.token);self.assertEqual(code,200);self.assertEqual(d['history_hole']['shots'][0]['club'],'7号铁')
  other=self.call('/auth/register',{'email':'history-other@example.test','password':'password-12345'})[1]['token'];self.assertEqual(self.call('/journey',{'action':'history_hole','round_id':'old-0','hole':1},other)[0],400)

 def test_compact_event_reply_reconstructs_full_snapshot(self):
  from services.api.view_delivery import compact
  before=self.call('/journey',{'action':'snapshot'},self.token)[1]['journey']
  known=compact(before,{})['journey_revisions']
  body=dict(action='core_event',operation_id='compact',compact_view=True,known_sections=known,event=dict(type='message',event_id='compact',text='可以记住',observed_at='2026-11-07T00:00:00+08:00'))
  code,d=self.call('/journey',body,self.token);self.assertEqual(200,code);self.assertTrue(d['journey_unchanged'])
  for path in d['journey_unchanged']:
   parts=path.split('.');old=before;new=d['journey']
   for part in parts[:-1]:old=old[part];new=new[part]
   new[parts[-1]]=old[parts[-1]]
  full=self.call('/journey',{'action':'snapshot'},self.token)[1]['journey']
  self.assertEqual(full,d['journey'])



 def test_generic_session_cannot_write_companion_aggregate(self):
  for action in ('create','event','snapshot','replay'):
   code,_=self.call('/round-state',{'action':action,'round_id':'companion-journey','operation_id':'bypass','event':{'type':'voice','event_id':'bypass','observed_at':'2026-11-22T01:00:00+00:00','text':'六杆'}},self.token)
   self.assertEqual(410,code)


 def test_shared_strategy_endpoint_uses_the_pinned_map_and_authenticated_model(self):
  from services.api.round_state import Engine,canonical
  from services.api.phoenix_demo import course
  from datetime import datetime,timezone
  self.call('/journey',{'action':'snapshot'},self.token);owner=self.server.store.user(self.token);engine=Engine(self.server.store.path,owner);mapped=course()
  try:
   state=engine.state('companion-journey');value=lambda n:dict(value=dict(distance=n,distance_type='carry',units='码'))
   state['journey']={'stage':'ready','round':{'id':'r','course':mapped['course_id'],'tee':'蓝Tee','start_hole':1},'profile':{'driver':value(260),'three_wood':value(240),'seven':value(160)},'quiet':False}
   state['facts']['context.course_snapshot']={'value':'m','valid':True};state['evidence']['m']={'id':'m','active':True,'phase':'final','data':mapped}
   engine.db.execute('UPDATE rounds SET state=%s WHERE owner=%s AND id=%s',(canonical(state),owner,'companion-journey'))
  finally:engine.close()
  request={'action':'offline_prepare','device_id':'phone-one','expected_version':0,'local_engine_version':1,'core_version':'old'}
  self.assertEqual(400,self.call('/journey',request,self.token)[0]);request['core_version']='1.6.0'
  code,prepared=self.call('/journey',request,self.token);self.assertEqual(200,code,prepared);lease=prepared['offline'];at=datetime.now(timezone.utc).isoformat()
  point=mapped['holes'][0]['simulation_positions']['tee'];point={k:point[k] for k in ('latitude','longitude','accuracy_m')}
  events=[]
  for seq,(command,data) in enumerate([('start',{}),('set_position',{'point':point})],1):
   event={'v':1,'semantics':2,'id':'typed'+str(seq),'at':at,'expected_revision':seq-1,'command':command,'data':data};events.append({'seq':seq,'event':{'type':'local_round_command','event_id':event['id'],'observed_at':at,'data':event}})
  code,synced=self.call('/journey',{**lease,'action':'offline_sync','events':events},self.token);self.assertEqual(200,code,synced)
  query={**lease,'action':'core_plan','intent':{'kind':'default'}}
  code,reply=self.call('/journey',query,self.token);self.assertEqual(200,code,reply);self.assertEqual('一号木',reply['strategy']['options'][0]['club'])
  self.assertEqual(401,self.call('/journey',query)[0]);self.assertEqual(409,self.call('/journey',{**query,'device_id':'other-phone'},self.token)[0]);self.assertEqual(400,self.call('/journey',{**query,'intent':{'owner':'other'}},self.token)[0])
  self.assertEqual(2,self.call('/journey',{'action':'snapshot'},self.token)[1]['journey']['version'])

if __name__=='__main__':unittest.main()
