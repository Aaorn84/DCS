from testing.database import TestDatabase
import unittest,tempfile,threading,json,urllib.request,urllib.error
from datetime import datetime,timezone
from services.api.server import make_server,Engine
from state_components import materialize
from shared_core import call,CORE_VERSION

class SharedWebHTTPTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TestDatabase();self.server=make_server(self.tmp.url,port=0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port);self.n=0
  self.token=self.request('/auth/register',{'email':'web@example.test','password':'password-12345'},auth=False)[1]['token']
  for word in ('可以记住','球友','好','好','260','160','偏右','跳过','东莞凤凰山（A+B蓝台演示）','蓝台','1'):
   status,reply=self.event('message',text=word);self.assertEqual(200,status,(word,reply))
  self.assertEqual('ready',reply['journey']['stage'])
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
 def request(self,path,body,auth=True):
  r=urllib.request.Request(self.base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+self.token} if auth else {})})
  try:
   with urllib.request.urlopen(r) as response:return response.status,json.load(response)
  except urllib.error.HTTPError as error:
   with error:return error.code,json.load(error)
 def envelope(self,kind,**values):
  self.n+=1;return {'action':'core_event','operation_id':'web'+str(self.n),'event':{'type':kind,'event_id':'web'+str(self.n),'observed_at':datetime.now(timezone.utc).isoformat(),**values}}
 def event(self,kind,**values):return self.request('/journey',self.envelope(kind,**values))
 def say(self,text):
  status,reply=self.event('message',text=text);self.assertEqual(200,status,(text,reply));return reply
 def model(self):
  engine=Engine(self.server.store.path,self.server.store.user(self.token))
  try:return engine.state('companion-journey')['journey']['offline_local_round']
  finally:engine.close()
 def gps(self,point,action='move'):
  status,reply=self.event('gps',data={**point,'simulation_source':'map_click','simulation_position_action':action});self.assertEqual(200,status,reply);return reply
 def start(self):
  reply=self.say('开始球局');self.assertTrue(reply['result']['shared_core']);self.assertEqual('shared',reply['journey']['core_runtime']);self.map=reply['journey']['simulation'];self.gps(self.map['positions']['tee']);return reply
 def test_start_map_strokes_score_and_replay_use_shared_core(self):
  status,pre=self.event('gps',data={'latitude':31,'longitude':121,'accuracy_m':2});self.assertEqual(200,status);self.assertTrue(pre['result']['ignored'])
  self.start();proposal=self.say('这杆怎么打');self.assertEqual('一号木',proposal['result']['strategy']['options'][0]['club']);before=self.model();self.say('1号木');self.assertEqual(0,len(self.model()['holes']['1']['rows']))
  reply=self.gps(self.map['positions']['fairway'],'shot');self.assertTrue(reply['result']['simulated_shot_recorded']);self.assertEqual(1,len(self.model()['holes']['1']['rows']))
  self.gps(self.map['positions']['fairway']);self.assertEqual(1,len(self.model()['holes']['1']['rows']))
  self.say('P杆');self.gps(self.map['positions']['green'],'shot');self.say('这洞四杆两推');reply=self.say('确认记录')
  self.assertEqual(4,reply['journey']['score_summary']['confirmed_subtotal']);self.assertEqual(4,len(reply['journey']['round_records']['clubs']))
  a=self.request('/journey',{'action':'snapshot'})[1];b=self.request('/journey',{'action':'replay'})[1];self.assertEqual(a,b)
 def test_web_commands_replay_in_the_same_mobile_engine_and_retry_is_idempotent(self):
  self.start();body=self.envelope('message',text='7号铁');code,first=self.request('/journey',body);self.assertEqual(200,code,first);revision=self.model()['revision'];self.assertEqual(200,self.request('/journey',body)[0]);self.assertEqual(revision,self.model()['revision'])
  bad={**body,'event':{**body['event'],'text':'P杆'}};self.assertEqual(409,self.request('/journey',bad)[0])
  self.gps(self.map['positions']['green'],'shot');model=self.model();engine=Engine(self.server.store.path,self.server.store.user(self.token))
  try:pack=materialize(engine.state('companion-journey')['journey']['shared_web_package']['items'][0])
  finally:engine.close()
  rebuilt=call('create',package=pack)
  for event in sorted(model['receipts'].values(),key=lambda e:e['expected_revision']):rebuilt=call('apply',state=rebuilt,event=event)
  self.assertEqual(model,rebuilt)
 def test_audio_records_once_and_map_only_completes_the_landing(self):
  self.start();self.say('7号铁');self.say('开启击球声音识别');self.say('音频检测到疑似击球');self.assertEqual(1,len(self.model()['holes']['1']['rows']))
  reply=self.say('击球声音等待结束');self.assertFalse(reply['journey']['shot_audio']['enabled']);self.assertIn('看到球',reply['result']['text']);reply=self.gps(self.map['positions']['green'],'shot');self.assertFalse(reply['result']['simulated_shot_recorded']);self.assertEqual(1,len(self.model()['holes']['1']['rows']))
 def test_navigation_does_not_add_a_shot_and_previous_hole_score_stays_scoped(self):
  self.start();self.say('7号铁');self.gps(self.map['positions']['green'],'shot');status,reply=self.event('simulation_hole',hole=2);self.assertEqual(200,status,reply);self.assertEqual(2,self.model()['hole']);self.assertEqual([],self.model()['holes']['2']['rows']);self.assertIn('第1洞',reply['result']['text'])
  self.say('这洞三杆两推');self.say('确认记录');model=self.model();self.assertEqual(3,model['holes']['1']['score']['total']);self.assertIsNone(model['holes']['2']['score']);self.assertEqual(2,model['hole'])
 def test_active_web_messages_do_not_fall_back_to_legacy_rule_reducers(self):
  self.start();body=self.envelope('message',text='7号铁');body['action']='event';code,reply=self.request('/journey',body);self.assertEqual(410,code,reply)
  self.assertEqual(400,self.request('/journey',self.envelope('unsupported_event'))[0])
 def test_finish_projects_archive_and_postgame_review_still_works(self):
  self.start();self.say('这洞四杆两推');self.say('确认记录');self.say('结束球局');self.say('确认结束');reply=self.say('分析总结本场');self.assertEqual(4,reply['journey']['score_summary']['confirmed_subtotal']);self.assertTrue(reply['result']['text'])
 def test_ob_and_yellow_water_relief_share_the_same_penalty_ledger(self):
  self.start();status,reply=self.event('simulation_hole',hole=3);self.assertEqual(200,status,reply);self.map=reply['journey']['simulation'];self.say('一号木')
  from services.api.phoenix_demo import course
  h=course()['holes'][2];ob={'longitude':114.15085,'latitude':22.70111,'accuracy_m':2,'simulation_hole':3}
  reply=self.gps(ob,'shot');self.assertIn('确认',reply['result']['text']);self.say('确认出界');model=self.model();self.assertEqual('relief_position',model['pending']['phase']);self.assertEqual(1,sum(r.get('amount',0) for r in model['holes']['3']['rows']))
  self.say('已回上一杆位置，坐标暂未知');self.assertIsNone(self.model()['pending']);self.assertEqual(1,len([r for r in self.model()['holes']['3']['rows'] if r['kind']=='stroke']))
  self.say('7号铁');water={'longitude':114.15060,'latitude':22.70111,'accuracy_m':2,'simulation_hole':3}
  self.gps(water,'shot');self.say('确认下水');self.say('黄桩');self.say('向后延线抛球');self.say('已确认越界点，合法抛球并停在救济区内，坐标暂未知');model=self.model();self.assertIsNone(model['pending']);self.assertEqual(2,sum(r.get('amount',0) for r in model['holes']['3']['rows']));self.assertEqual(2,len([r for r in model['holes']['3']['rows'] if r['kind']=='stroke']))
 def test_partial_score_and_carry_changes_are_visible_without_false_confirmation(self):
  self.start();self.say('这洞六杆');self.assertIsNone(self.model()['holes']['1']['score']);reply=self.say('两推');self.assertEqual(6,self.model()['draft']['total']);self.assertEqual(2,self.model()['draft']['putts']);self.say('确认记录')
  self.event('simulation_hole',hole=2);reply=self.say('3号木210，5号木200');values={c['label']:c['high'] for c in reply['journey']['core_carry']};self.assertEqual(210,values['3号木']);self.assertEqual(200,values['5号木'])
 def test_total_only_after_a_known_green_landing_does_not_ask_putts_again(self):
  self.start();self.say('7号铁');self.gps(self.map['positions']['green'],'shot');reply=self.say('这洞三杆');self.assertNotIn('几推',reply['result']['text']);self.assertEqual(2,self.model()['draft']['putts'])
 def test_same_event_id_with_a_new_operation_is_not_a_second_stroke(self):
  self.start();self.say('7号铁');body=self.envelope('gps',data={**self.map['positions']['green'],'simulation_source':'map_click','simulation_position_action':'shot'});self.assertEqual(200,self.request('/journey',body)[0]);before=self.model();body['operation_id']='another-operation';code,reply=self.request('/journey',body);self.assertEqual(200,code,reply);self.assertTrue(reply['result']['duplicate']);self.assertEqual(before,self.model())
  body['operation_id']='yet-another';body['event']['data']['latitude']+=.0001;self.assertEqual(400,self.request('/journey',body)[0])
 def test_unknown_or_future_events_cannot_fall_back_or_mutate_the_ledger(self):
  self.start();before=self.model();future=self.envelope('message',text='7号铁');future['event']['observed_at']='2099-01-01T00:00:00Z';self.assertEqual(400,self.request('/journey',future)[0]);self.assertEqual(before,self.model())
  self.say('7号铁');self.gps(self.map['positions']['green'],'shot');self.say('可能出界');version=self.model()['revision'];code,_=self.event('simulation_hole',hole=3);self.assertEqual(400,code);self.assertEqual(version,self.model()['revision'])
 def test_next_round_keeps_recent_history_in_the_pinned_shared_package(self):
  self.start();old_id=self.model()['round_id'];self.say('一号木');self.gps(self.map['positions']['fairway'],'shot');self.say('P杆');self.gps(self.map['positions']['green'],'shot');self.say('这洞四杆两推');self.say('确认记录');self.say('结束球局');self.say('确认结束');self.assertEqual(200,self.event('next_round')[0])
  for word in ('东莞凤凰山（A+B蓝台演示）','蓝台','1'):reply=self.say(word)
  self.assertEqual('ready',reply['journey']['stage']);self.start();engine=Engine(self.server.store.path,self.server.store.user(self.token))
  try:pack=materialize(engine.state('companion-journey')['journey']['shared_web_package']['items'][0])
  finally:engine.close()
  self.assertTrue(pack['history_by_hole']['1']);self.assertEqual(old_id,pack['history_by_hole']['1'][0]['round_id'])
 def test_immutable_map_is_not_embedded_in_the_per_message_state_document(self):
  self.start();engine=Engine(self.server.store.path,self.server.store.user(self.token))
  try:
   raw=engine.db.execute('SELECT state FROM rounds WHERE owner=%s AND id=%s',(engine.owner,'companion-journey')).fetchone()[0];self.assertLess(len(raw),100000)
   state=json.loads(raw);self.assertIn('__caddie_list_component_v1__',state['journey']['shared_web_package']['items'])
  finally:engine.close()
 def test_web_waits_for_native_release_then_continues_the_same_core_model(self):
  from offline_sync import prepare,synchronize,release
  engine=Engine(self.server.store.path,self.server.store.user(self.token))
  try:
   state=engine.state('companion-journey');p=prepare(engine,{'device_id':'native-phone','expected_version':state['version'],'local_engine_version':1,'core_version':CORE_VERSION});lease=p['offline'];point=p['offline_package']['package']['course']['holes'][0]['simulation_positions']['tee'];at=datetime.now(timezone.utc).isoformat()
   events=[]
   for seq,(command,data) in enumerate([('start',{}),('set_position',{'point':point})],1):
    event={'v':1,'semantics':2,'id':'native'+str(seq),'at':at,'expected_revision':seq-1,'command':command,'data':data};events.append({'seq':seq,'event':{'type':'local_round_command','event_id':event['id'],'observed_at':at,'data':event}})
   synchronize(engine,{**lease,'events':events});self.assertEqual(409,self.event('message',text='这杆怎么打')[0]);release(engine,{**lease,'cursor':2})
  finally:engine.close()
  before=self.model();reply=self.say('这杆怎么打');self.assertTrue(reply['result']['shared_core']);self.assertEqual(before,self.model());self.say('7号铁');self.assertEqual('7号铁',self.model()['selection']['club'])
 def test_postgame_services_cannot_silently_rewrite_the_core_score(self):
  self.start();self.say('这洞四杆两推');self.say('确认记录');self.say('结束球局');self.say('确认结束');before=self.model();self.say('分析总结，并更正第1洞6杆2推');self.assertEqual(before,self.model());self.say('安静');reply=self.request('/journey',{'action':'snapshot'})[1];self.assertEqual(['继续'],reply['journey']['choices'])
 def test_strategy_cache_is_reused_only_until_ball_position_changes(self):
  self.start();first=self.say('这杆怎么打');second=self.say('这杆怎么打');self.assertFalse(first['result']['strategy_cache_hit']);self.assertTrue(second['result']['strategy_cache_hit']);self.assertEqual(first['result']['strategy'],second['result']['strategy'])
  self.gps(self.map['positions']['green']);changed=self.say('这杆怎么打');self.assertFalse(changed['result']['strategy_cache_hit']);self.assertNotEqual(second['result']['strategy'],changed['result']['strategy'])
 def test_provisional_location_keeps_original_tee_distance_and_does_not_add_a_shot(self):
  self.start();tee=self.map['positions']['tee'];self.say('一号木');self.gps(self.map['positions']['fairway'],'shot');self.say('可能出界');self.say('暂定球用一号木已宣告并打');self.say('确认出界');self.gps(self.map['positions']['green']);self.say('已到暂定球位置');model=self.model();self.assertIsNone(model['pending']);strokes=[r for r in model['holes']['1']['rows'] if r['kind']=='stroke'];self.assertEqual(2,len(strokes));self.assertEqual(tee['latitude'],strokes[1]['origin']['latitude']);self.assertEqual(self.map['positions']['green']['latitude'],strokes[1]['landing']['latitude'])
 def test_yellow_relief_current_position_confirmation_finishes_without_a_loop(self):
  self.start();self.say('7号铁');self.gps(self.map['positions']['fairway'],'shot');self.say('确认下水');self.say('黄桩');self.say('向后延线抛球');self.say('已确认最后越界点');self.say('已在合法位置抛球');self.say('球停在救济区内');self.gps(self.map['positions']['fairway']);self.say('确认在当前位置');model=self.model();self.assertIsNone(model['pending']);self.assertEqual(1,sum(r.get('amount',0) for r in model['holes']['1']['rows']));self.assertEqual(1,len([r for r in model['holes']['1']['rows'] if r['kind']=='stroke']))
 def test_postgame_named_hole_and_details_use_the_separate_app_service(self):
  self.start();self.say('一号木');self.gps(self.map['positions']['fairway'],'shot');self.say('这洞四杆两推');self.say('确认记录');self.say('结束球局');self.say('确认结束')
  before=self.model();self.say('分析总结');self.say('复盘某一洞');reply=self.say('A1');self.assertIn('第1洞4杆',reply['result']['text']);self.assertNotIn('我在听',reply['result']['text']);self.assertEqual(before,self.model())
  reply=self.say('播报详细数据');self.assertIn('FIR',reply['result']['text']);self.assertEqual(before,self.model())
 def test_retired_entry_is_rejected_even_before_first_questions(self):
  token=self.request('/auth/register',{'email':'retired@example.test','password':'password-12345'},auth=False)[1]['token'];old=self.token;self.token=token
  try:
   body=self.envelope('message',text='可以记住');body['action']='event';self.assertEqual(410,self.request('/journey',body)[0]);self.assertEqual('memory',self.request('/journey',{'action':'snapshot'})[1]['journey']['stage'])
   self.assertEqual(410,self.request('/round-state',{'action':'create','round_id':'old-round'})[0])
   body['action']='core_event';body['event']['protocol_version']=111;self.assertEqual(400,self.request('/journey',body)[0])
  finally:self.token=old
 def test_generic_sync_cannot_change_a_live_core_score_or_create_parallel_scores(self):
  self.start();self.say('这洞四杆两推');self.say('确认记录');before=self.model()
  body=dict(operationId='parallel-score',kind='round',id='parallel',baseVersion=0,data={'course':'x','scores':[None]*18,'status':'finished'})
  self.assertEqual(410,self.request('/sync',body)[0]);self.assertEqual(before,self.model())
  with self.server.store.connect() as db:self.assertEqual(0,db.execute("SELECT count(*) AS n FROM records WHERE kind='round'").fetchone()['n'])
 def test_finish_archives_the_pinned_course_basis_and_replay_preserves_it(self):
  from course_history_comparison import basis
  self.start();self.say('这洞四杆两推');self.say('确认记录');self.say('结束球局');self.say('确认结束')
  engine=Engine(self.server.store.path,self.server.store.user(self.token))
  try:
   state=engine.state('companion-journey');saved=state['journey']['history'][-1]['course_basis']
   self.assertEqual([basis(state)],saved);self.assertEqual(18,len(saved[0]));self.assertEqual({'par':4,'published_yardage':380},saved[0]['11']);self.assertEqual({'par':3,'published_yardage':130},saved[0]['17'])
   self.assertEqual(saved,engine.replay('companion-journey')['journey']['history'][-1]['course_basis'])
  finally:engine.close()
 def test_conservative_request_replans_after_finder_and_carry_without_repeating_the_question(self):
  self.start();alternative=self.say('有没有其他方案');self.assertRegex(alternative['result']['strategy']['options'][0]['club'],r'^[345]号铁$');first=self.say('有没有保守方案');self.assertEqual('finder_club',first['result']['strategy']['question']);recorded=self.say('保底开球杆 5号木 200码')
  self.assertEqual('5号木',recorded['result']['strategy']['options'][0]['club']);self.assertEqual(200,recorded['result']['strategy']['options'][0]['carry_yards']);self.assertEqual(0,len(self.model()['holes']['1']['rows']))
  again=self.say('有没有保守方案');self.assertEqual('5号木',again['result']['strategy']['options'][0]['club']);self.assertNotIn('请补充保底开球杆',again['result']['text']);self.assertEqual(200,self.model()['profile']['bag_overrides']['5号木']['high'])
  self.assertEqual(self.request('/journey',{'action':'snapshot'})[1],self.request('/journey',{'action':'replay'})[1])
