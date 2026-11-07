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
if __name__=='__main__':unittest.main()
