import unittest,tempfile,threading,json,urllib.request,urllib.error
from services.api.server import make_server
class JourneyHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.server=make_server(self.tmp.name+'/db',port=0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port);self.n=0
  self.token=self.call('/auth/register',{'email':'j@example.test','password':'password-12345'})[1]['token']
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def call(self,path,body,token=None):
  req=urllib.request.Request(self.base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
  try:
   with urllib.request.urlopen(req) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:
   with e:return e.code,json.load(e)
 def msg(self,text):
  self.n+=1;return self.call('/journey',{'action':'event','operation_id':'op'+str(self.n),'event':{'type':'message','event_id':'e'+str(self.n),'observed_at':'2026-11-07T00:00:00+08:00','text':text}},self.token)
 def test_end_to_end_from_first_use_to_return(self):
  self.assertEqual(self.call('/journey',{'action':'snapshot'},self.token)[1]['journey']['stage'],'memory')
  for t in ['可以记住','阿明','可以提醒','不记录击球','230','140','偏右','演示球场（合成）','蓝台','1','轻松打球','状态不错','开始球局','这洞五杆','两推','确认','结束球局','确认结束','挺开心','今天到这里','下一场']:
   code,d=self.msg(t);self.assertEqual(code,200,(t,d))
   if t=='这洞五杆':self.assertTrue(d['result']['speak_allowed'])
  self.assertEqual(d['journey']['stage'],'course');self.assertEqual(d['journey']['history'][0]['confirmed_subtotal'],5)
  a=self.call('/journey',{'action':'snapshot'},self.token)[1]
  b=self.call('/journey',{'action':'replay'},self.token)[1];self.assertEqual(a,b)
 def test_requires_authentication(self):self.assertEqual(self.call('/journey',{'action':'snapshot'})[0],401)
 def test_account_isolation(self):
  self.msg('可以记住');other=self.call('/auth/register',{'email':'other@example.test','password':'password-12345'})[1]['token']
  self.assertEqual(self.call('/journey',{'action':'snapshot'},other)[1]['journey']['stage'],'memory')
 def test_reject_body_owner_and_stale_version(self):
  self.assertEqual(self.call('/journey',{'action':'event','operation_id':'x','event':{'owner':'other'}},self.token)[0],400)
  self.msg('可以记住')
  self.assertEqual(self.call('/journey',{'action':'event','operation_id':'stale','expected_version':0,'event':{'type':'message','event_id':'s','text':'阿明','observed_at':'2026-11-07T00:00:00+08:00'}},self.token)[0],409)
 def test_lost_receipt_after_progress_does_not_repeat_old_question(self):
  body={'action':'event','operation_id':'retry','event':{'type':'message','event_id':'retry','observed_at':'2026-11-07T00:00:00+08:00','text':'可以记住'}}
  self.assertEqual(self.call('/journey',body,self.token)[0],200)
  self.msg('阿明')
  code,d=self.call('/journey',body,self.token);self.assertEqual(code,200)
  self.assertEqual(d['result']['text'],'');self.assertFalse(d['result']['speak_allowed']);self.assertEqual(d['journey']['stage'],'proactive')
 def test_default_yards_and_natural_reminder_permission(self):
  self.msg('可以记住')
  body={'action':'event','operation_id':'name','event':{'type':'message','protocol_version':1,'event_id':'name','observed_at':'2026-11-07T00:00:00+08:00','text':'测试球友'}}
  code,d=self.call('/journey',body,self.token);self.assertEqual(code,200);self.assertEqual(d['journey']['stage'],'proactive');self.assertEqual(d['journey']['distance_unit'],'码')
  code,d=self.msg('no problem');self.assertEqual(code,200);self.assertTrue(d['journey']['profile']['proactive']['value']);self.assertEqual(d['journey']['stage'],'shot_recording')
  code,d=self.msg('我不习惯使用码，我更习惯用米');self.assertEqual(code,200);self.assertEqual(d['journey']['distance_unit'],'米');self.assertEqual(d['journey']['stage'],'shot_recording')
  self.assertEqual(self.call('/journey',{'action':'snapshot'},self.token)[1],self.call('/journey',{'action':'replay'},self.token)[1])

 def test_ball_rule_relief_score_and_replay(self):
  from datetime import datetime,timedelta,timezone
  from services.api.phoenix_demo import preview
  def turn(text=None,**extra):
   self.n+=1
   stamp=datetime.now(timezone.utc).isoformat()
   event=dict(type='message' if text is not None else extra.pop('type'),event_id='rules'+str(self.n),observed_at=stamp,**extra)
   if text is not None:event['text']=text
   code,data=self.call('/journey',dict(action='event',operation_id=event['event_id'],event=event),self.token)
   self.assertEqual(200,code,data)
   return data
  for word in ('可以记住','球友','好','好','260','160','偏右','东莞凤凰山（A+B蓝台演示）','蓝台','3','轻松打球','开始球局'):
   turn(word)
  turn(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
  turn('确认下水')
  turn('红桩')
  turn('向后延线抛球')
  turn('已确认最后越界点')
  turn('已在合法位置抛球')
  turn('球停在救济区内')
  # Relief must have a current ball position before the score can be confirmed.
  turn(type='gps',data=dict(preview(3)['positions']['fairway'],simulation_source='map_click'))
  turn('就在这里完成救济')
  data=turn('第3洞4杆，2推，1罚杆')
  self.assertEqual(1,data['journey']['round_records']['score_draft']['penalties'])
  self.assertEqual([1,3,4],[r['stroke_number'] for r in data['journey']['round_records']['clubs']])
  confirmed=turn('确认')['result']
  self.assertTrue(confirmed.get('saved'),confirmed)
  data=turn('撤销上次罚杆')
  self.assertIn('重新确认',data['result']['text'])
  self.assertEqual('penalties',data['journey']['round_records']['score_draft']['awaiting'])
  self.assertEqual(self.call('/journey',{'action':'snapshot'},self.token)[1],self.call('/journey',{'action':'replay'},self.token)[1])
 def test_history_metadata_is_paged_and_shots_load_only_on_explicit_request(self):
  from services.api.round_state import Engine,canonical
  self.call('/journey',{'action':'snapshot'},self.token);owner=self.server.store.user(self.token)
  e=Engine(self.server.store.path,owner)
  try:
   s=e.state('companion-journey');s['journey']=dict(stage='postgame',round=dict(id='current',course='course',finished=True),profile={},coach={'enabled':False},history=[],quiet=False,memory_allowed=True)
   for i in range(25):s['journey']['history'].append(dict(round=dict(id='old-'+str(i),course='course',finished=True),confirmed_holes=18,confirmed_subtotal=80,scores=[dict(hole=1,total=4,putts=2,penalties=0)],hole_history={'1':dict(signature='s',shots=[dict(id='shot',club='7号铁',stroke_number=1,distance_m=140)])}))
   e.db.execute('UPDATE rounds SET state=? WHERE owner=? AND id=?',(canonical(s),owner,'companion-journey'));e.compact('companion-journey')
  finally:e.close()
  code,d=self.call('/journey',{'action':'snapshot'},self.token);self.assertEqual(code,200);j=d['journey'];self.assertEqual(len(j['history']),20);self.assertEqual(j['history_count'],25);self.assertNotIn('hole_history',j['history'][0]);self.assertNotIn('scores',j['history'][0])
  code,d=self.call('/journey',{'action':'history','offset':20,'limit':20},self.token);self.assertEqual(code,200);self.assertEqual(len(d['history_page']['rounds']),5)
  code,d=self.call('/journey',{'action':'history_hole','round_id':'old-0','hole':1},self.token);self.assertEqual(code,200);self.assertEqual(d['history_hole']['shots'][0]['club'],'7号铁')
  other=self.call('/auth/register',{'email':'history-other@example.test','password':'password-12345'})[1]['token'];self.assertEqual(self.call('/journey',{'action':'history_hole','round_id':'old-0','hole':1},other)[0],400)

 def test_compact_event_reply_reconstructs_full_snapshot(self):
  from services.api.view_delivery import compact
  before=self.call('/journey',{'action':'snapshot'},self.token)[1]['journey']
  known=compact(before,{})['journey_revisions']
  body=dict(action='event',operation_id='compact',compact_view=True,known_sections=known,event=dict(type='message',event_id='compact',text='可以记住',observed_at='2026-11-07T00:00:00+08:00'))
  code,d=self.call('/journey',body,self.token);self.assertEqual(200,code);self.assertTrue(d['journey_unchanged'])
  for path in d['journey_unchanged']:
   parts=path.split('.');old=before;new=d['journey']
   for part in parts[:-1]:old=old[part];new=new[part]
   new[parts[-1]]=old[parts[-1]]
  full=self.call('/journey',{'action':'snapshot'},self.token)[1]['journey']
  self.assertEqual(full,d['journey'])

if __name__=='__main__':unittest.main()
