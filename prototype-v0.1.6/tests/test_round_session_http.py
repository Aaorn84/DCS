import datetime
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from services.api.server import make_server

COURSE=dict(course_id='synthetic',map_version='1',crs='WGS84',synthetic=True,holes=[
 dict(number=1,par=4,bbox=[120.999,30.999,121.004,31.002],objects=[dict(id='g1',kind='green_center',latitude=31.001,longitude=121.003)])])


class SessionHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=self.tmp.name+'/test.sqlite'
  self.start();self.n=0
  self.token=self.call('/auth/register',dict(email='a@example.test',password='safe-password-123'))[1]['token']
  self.call('/round-state',dict(action='create',round_id='r'),self.token)
 def start(self):
  self.server=make_server(self.path,port=0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
  self.base='http://127.0.0.1:'+str(self.server.server_port)
 def stop(self):self.server.shutdown();self.server.server_close();self.thread.join()
 def tearDown(self):self.stop();self.tmp.cleanup()
 def call(self,path,data=None,token=None):
  req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,
     headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
  try:
   with urllib.request.urlopen(req,timeout=5) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:
   with e:return e.code,json.load(e)
 def event(self,type,**kw):
  self.n+=1
  body=dict(action='event',round_id='r',operation_id='op'+str(self.n),event=dict(type=type,event_id='e'+str(self.n),observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),**kw))
  return self.call('/round-state',body,self.token)
 def inputs(self):
  self.assertEqual(self.event('course',data=COURSE)[0],200)
  self.assertEqual(self.event('gps',data=dict(latitude=31,longitude=121.001,accuracy_m=2))[0],200)
 def test_authenticated_three_input_round_trip(self):
  self.inputs()
  distance=self.event('voice',text='还有多少米')[1]['result']
  self.assertEqual(distance['distance']['origin'],'device_gps')
  self.assertFalse(distance['distance']['carry'])
  self.assertIn('几推',self.event('voice',text='这洞六杆')[1]['result']['text'])
  self.assertIn('罚杆',self.event('voice',text='两推')[1]['result']['text'])
  self.event('voice',text='没有罚杆')
  before=self.call('/round-state',dict(action='snapshot',round_id='r'),self.token)[1]['state']
  self.assertNotIn('holes.1.total',before['facts'])
  result=self.event('voice',text='确认')[1]
  self.assertTrue(result['result']['saved']);self.assertEqual(result['state']['facts']['holes.1.total']['value'],6)
  self.assertEqual(self.call('/records',token=self.token)[1]['records'],[])
  self.assertEqual(self.call('/round-state',dict(action='replay',round_id='r'),self.token)[1]['state'],result['state'])
  self.stop();self.start()
  self.assertEqual(self.call('/round-state',dict(action='snapshot',round_id='r'),self.token)[1]['state'],result['state'])
  self.event('voice',text='撤销上一条记分')
  self.assertIsNone(self.call('/round-state',dict(action='snapshot',round_id='r'),self.token)[1]['state']['facts']['holes.1.total']['value'])
 def test_authentication_and_owner_forgery(self):
  self.assertEqual(self.call('/round-state',dict(action='snapshot',round_id='r'))[0],401)
  bob=self.call('/auth/register',dict(email='b@example.test',password='safe-password-123'))[1]['token']
  self.assertNotEqual(self.call('/round-state',dict(action='snapshot',round_id='r',owner='alice'),bob)[0],200)
  self.assertEqual(self.event('voice',text='hi',owner='b')[0],400)
 def test_transport_retry_does_not_duplicate(self):
  body=dict(action='event',round_id='r',operation_id='same',event=dict(type='voice',event_id='same',text='安静',observed_at='2026-11-06T00:00:00Z'))
  a=self.call('/round-state',body,self.token)
  self.assertEqual(a,self.call('/round-state',body,self.token))
  body['event']['text']='继续'
  self.assertEqual(self.call('/round-state',body,self.token)[0],409)
 def test_stale_client_version_returns_conflict(self):
  self.inputs()
  body=dict(action='event',round_id='r',operation_id='stale',expected_version=0,event=dict(type='voice',event_id='stale',text='确认',observed_at='2026-11-06T00:00:00Z'))
  code,result=self.call('/round-state',body,self.token)
  self.assertEqual(code,409);self.assertEqual(result['current']['version'],2)
 def test_quiet_reply_has_no_tts_permission(self):
  self.inputs();self.event('voice',text='安静')
  r=self.event('voice',text='还有多少')[1]['result']
  self.assertFalse(r['speak_allowed'])
  self.assertTrue(self.event('voice',text='继续')[1]['result']['speak_allowed'])
 def test_does_not_expose_raw_engine_commands(self):
  self.assertEqual(self.event('voice',text='hi',operations=[])[0],400)
  self.assertEqual(self.event('patch',data={})[0],400)
