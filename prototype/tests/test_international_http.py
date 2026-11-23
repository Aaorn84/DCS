from testing.database import TestDatabase
import unittest,tempfile,threading,json,urllib.request,urllib.error
from services.api.server import make_server
class InternationalHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TestDatabase();self.server=make_server(self.tmp.url,port=0);self.t=threading.Thread(target=self.server.serve_forever,daemon=True);self.t.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
  self.token=self.call('/auth/register',{'email':'international@example.test','password':'password-12345'})[1]['token']
 def tearDown(self):self.server.shutdown();self.server.server_close();self.t.join();self.tmp.cleanup()
 def call(self,path,body,token=None):
  req=urllib.request.Request(self.base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
  try:
   with urllib.request.urlopen(req) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:
   with e:return e.code,json.load(e)
 def event(self,**kw):return {'action':'event','operation_id':'op','event':{'event_id':'one','observed_at':'2026-11-08T00:00:00Z','type':'configure','configuration':{'locale':'ja-JP','market_region':'JP'},**kw}}
 def test_auth_and_owner_isolation(self):
  self.assertEqual(self.call('/international',{},None)[0],401)
  self.assertEqual(self.call('/international',self.event(),self.token)[0],200)
  token=self.call('/auth/register',{'email':'second@example.test','password':'password-12345'})[1]['token']
  self.assertEqual(self.call('/international',{},token)[1]['configuration']['locale'],'zh-CN')
 def test_config_and_durable_replay(self):
  code,out=self.call('/international',self.event(),self.token);self.assertEqual(code,200);self.assertEqual(out['configuration']['locale'],'ja-JP');self.assertFalse(out['capabilities']['production_ready'])
  self.assertEqual(self.call('/international',{'action':'snapshot'},self.token)[1],self.call('/international',{'action':'replay'},self.token)[1])
 def test_unknown_fields_and_stale_version(self):
  self.assertEqual(self.call('/international',self.event(owner='other'),self.token)[0],400)
  self.assertEqual(self.call('/international',self.event(),self.token)[0],200)
  body=self.event(event_id='second');body.update(operation_id='second',expected_version=0)
  self.assertEqual(self.call('/international',body,self.token)[0],409)
 def test_legacy_aggregate_not_changed(self):
  self.call('/international',self.event(),self.token)
  self.assertEqual(self.call('/journey',{},self.token)[1]['journey']['stage'],'memory')
 def test_low_confidence_never_commits_a_shot(self):
  body=self.event(type='semantic',candidate={'type':'execution_report','slots':{'club':'7i'},'confidence':.5});del body['event']['configuration']
  code,out=self.call('/international',body,self.token);self.assertEqual(code,200);self.assertEqual(out['result']['status'],'clarify');self.assertEqual(out['journey']['stage'],'memory')
if __name__=='__main__':unittest.main()
