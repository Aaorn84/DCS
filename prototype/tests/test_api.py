from testing.database import TestDatabase
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from services.api.server import Store, Problem, make_server, reply


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=TestDatabase()
        self.store=Store(self.temp.url)
        self.alice=self.store.auth({'email':'alice@example.test','password':'safe-password-123'},True)
        self.bob=self.store.auth({'email':'bob@example.test','password':'safe-password-123'},True)
        self.user=self.alice['user']['id']

    def tearDown(self):
        self.temp.cleanup()

    def op(self, **overrides):
        return {'operationId':'op-1','kind':'memory','id':'memory-1','baseVersion':0,
                'data':{'text':'失误后先让我安静一下'},**overrides}

    def test_auth_and_logout(self):
        self.assertEqual(self.store.user(self.alice['token']),self.user)
        with self.assertRaises(Problem):
            self.store.auth({'email':'alice@example.test','password':'wrong-password'})
        self.store.logout(self.alice['token'])
        with self.assertRaises(Problem):self.store.user(self.alice['token'])

    def test_ownership_and_idempotency(self):
        first=self.store.apply(self.user,self.op())
        self.assertEqual(first,self.store.apply(self.user,self.op()))
        self.assertEqual(len(self.store.snapshot(self.user)),1)
        self.assertEqual(self.store.snapshot(self.bob['user']['id']),[])
        self.store.apply(self.bob['user']['id'],self.op(data={'text':'不同用户'}))
        self.assertEqual(self.store.snapshot(self.user)[0]['data']['text'],'失误后先让我安静一下')

    def test_operation_id_payload_mismatch(self):
        self.store.apply(self.user,self.op())
        with self.assertRaises(Problem) as ctx:self.store.apply(self.user,self.op(data={'text':'changed'}))
        self.assertEqual(ctx.exception.status,409)

    def test_concurrent_change_conflicts(self):
        self.store.apply(self.user,self.op())
        self.store.apply(self.user,self.op(operationId='op-2',baseVersion=1,data={'text':'new'}))
        with self.assertRaises(Problem) as ctx:self.store.apply(self.user,self.op(operationId='op-3',baseVersion=1))
        self.assertEqual(ctx.exception.extra['current']['version'],2)

    def test_delete_scrubs_and_prevents_resurrection(self):
        self.store.apply(self.user,self.op())
        deleted=self.store.apply(self.user,self.op(operationId='delete',baseVersion=1,deleted=True,data={}))
        self.assertTrue(deleted['deleted']);self.assertEqual(deleted['data'],{})
        # Retrying a previously acknowledged write must not leak deleted text.
        self.assertEqual(self.store.apply(self.user,self.op()),deleted)
        with self.assertRaises(Problem):self.store.apply(self.user,self.op(operationId='restore',baseVersion=2))
        with self.store.connect() as db:
            receipts=' '.join(r['result'] for r in db.execute('SELECT result FROM operations'))
            self.assertNotIn('失误',receipts)

    def test_independent_round_writes_updates_deletes_and_retries_are_closed(self):
        from services.api.server import Engine
        engine=Engine(self.store.path,self.user);engine.create('companion-journey')
        before=engine.state('companion-journey')
        try:
            for overrides in ({},{'baseVersion':1},{'deleted':True},{'operationId':'retry'}):
                op=self.op(kind='round',data={'course':'x','scores':[None]*18,'status':'active'},**overrides)
                with self.assertRaises(Problem) as ctx:self.store.apply(self.user,op)
                self.assertEqual(410,ctx.exception.status)
            self.assertEqual(before,engine.state('companion-journey'))
            with self.store.connect() as db:
                self.assertEqual(0,db.execute('SELECT count(*) AS n FROM records').fetchone()['n']);self.assertEqual(0,db.execute('SELECT count(*) AS n FROM operations').fetchone()['n'])
        finally:engine.close()

    def test_record_snapshot_does_not_expose_retired_round_documents(self):
        with self.store.connect() as db:
            db.execute('INSERT INTO records VALUES(%s,%s,%s,%s,%s,%s,%s)',(self.user,'round','old',1,0,json.dumps({'scores':[None]*18}),0))
        self.store.apply(self.user,self.op())
        self.assertEqual(['memory'],[r['kind'] for r in self.store.snapshot(self.user)])

    def test_model_context_is_scoped_and_deleted_memory_absent(self):
        self.store.apply(self.user,self.op(data={'text':'ALICE_PRIVATE'}))
        self.store.apply(self.bob['user']['id'],self.op(data={'text':'BOB_PRIVATE'}))
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b'{"choices":[{"message":{"content":"hello"}}]}'
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':'test-only'}), patch('urllib.request.urlopen',return_value=Response()) as url:
            reply(self.store,self.user,{'message':'hi'})
            payload=json.loads(url.call_args.args[0].data)
            self.assertIn('ALICE_PRIVATE',payload['messages'][0]['content'])
            self.assertNotIn('BOB_PRIVATE',payload['messages'][0]['content'])
            self.store.apply(self.user,self.op(operationId='delete',baseVersion=1,deleted=True,data={}))
            reply(self.store,self.user,{'message':'hi'})
            self.assertNotIn('ALICE_PRIVATE',json.loads(url.call_args.args[0].data)['messages'][0]['content'])


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=TestDatabase();self.server=make_server(self.temp.url,port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def call(self,path,data=None,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        request=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=5) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as e:
            with e:return e.code,json.load(e)
    def test_full_account_sync_flow(self):
        self.assertEqual(self.call('/records')[0],401)
        code,auth=self.call('/auth/register',{'email':'http@example.test','password':'safe-password-123'})
        self.assertEqual(code,200);token=auth['token']
        op={'operationId':'p1','kind':'profile','id':'profile','baseVersion':0,
            'data':{'name':'阿明','style':'温暖简洁','quiet':True}}
        self.assertEqual(self.call('/sync',op,token)[0],200)
        self.assertEqual(self.call('/records',token=token)[1]['records'][0]['data']['name'],'阿明')
        with patch.dict(os.environ,{'DEEPSEEK_API_KEY':''}):
            self.assertEqual(self.call('/chat',{'message':'紧张'},token)[1]['provider'],'demo')
        self.assertEqual(self.call('/auth/logout',{},token)[0],200)
        self.assertEqual(self.call('/records',token=token)[0],401)

    def test_authenticated_round_sync_route_rejects_create_change_and_delete(self):
        code,auth=self.call('/auth/register',{'email':'round@example.test','password':'safe-password-123'})
        self.assertEqual(200,code);token=auth['token']
        for deleted in (False,True):
            op={'operationId':'round','kind':'round','id':'round','baseVersion':0,'deleted':deleted,'data':{'course':'x','scores':[None]*18,'status':'active'}}
            self.assertEqual(410,self.call('/sync',op,token)[0])
        self.assertEqual([],self.call('/records',token=token)[1]['records'])

if __name__=='__main__':unittest.main()
