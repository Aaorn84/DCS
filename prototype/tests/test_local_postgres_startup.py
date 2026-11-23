"""Startup fault tests use private temp paths, never the application cluster."""
import importlib.util,json,os,socket,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'prototype/scripts/local_postgres.py'
def module():
 spec=importlib.util.spec_from_file_location('local_pg_under_test',SOURCE);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def wait_file(path):
 deadline=time.monotonic()+5
 while not path.exists():
  if time.monotonic()>deadline:raise AssertionError('child did not reach synchronization point')
  time.sleep(.01)

class LocalPostgresStartupTests(unittest.TestCase):
 def test_atomic_config_failure_preserves_previous_complete_config(self):
  pg=module()
  with tempfile.TemporaryDirectory() as tmp,patch.object(pg,'RUNTIME',Path(tmp)):
   pg.save_config({'initialized':True,'value':'original'})
   with patch.object(pg.os,'replace',side_effect=OSError('disk unavailable')):
    with self.assertRaises(OSError):pg.save_config({'initialized':False})
   self.assertEqual({'initialized':True,'value':'original'},pg.config())
   self.assertEqual(['postgres.json'],[p.name for p in Path(tmp).iterdir()]);self.assertEqual(0o600,(Path(tmp)/'postgres.json').stat().st_mode&0o777)
 def test_process_exit_releases_initialization_lock_and_wait_is_bounded(self):
  pg=module()
  with tempfile.TemporaryDirectory() as tmp:
   ready=Path(tmp)/'ready'
   code=f"import sys,time;from pathlib import Path;sys.path.insert(0,{str(SOURCE.parent)!r});import local_postgres as p;p.RUNTIME=Path({tmp!r});\nwith p.cluster_lock():\n Path({str(ready)!r}).touch();time.sleep(20)"
   child=subprocess.Popen([sys.executable,'-B','-c',code],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   try:
    wait_file(ready)
    with patch.object(pg,'RUNTIME',Path(tmp)):
     with self.assertRaisesRegex(RuntimeError,'busy'):
      with pg.cluster_lock(timeout=.02):pass
     child.kill();child.communicate(timeout=5)
     with pg.cluster_lock(timeout=.1):pass
   finally:
    if child.poll() is None:child.kill();child.communicate(timeout=5)
 def test_concurrent_start_calls_cannot_read_partial_initialization(self):
  with tempfile.TemporaryDirectory() as tmp:
   code=f'''import sys,json,time
from pathlib import Path
sys.path.insert(0,{str(SOURCE.parent)!r})
import local_postgres as p
p.RUNTIME=Path({tmp!r})
def provision(port):
 if not (p.RUNTIME/'postgres.json').exists():
  p.save_config({{'initialized':False}})
  time.sleep(.15)
  p.save_config({{'initialized':True}})
  with (p.RUNTIME/'provisions').open('a') as f:f.write('once\\n')
 result=p.config()
 assert result['initialized'] is True
 return result
p._start_locked=provision
print(json.dumps(p.start()))
'''
   children=[subprocess.Popen([sys.executable,'-B','-c',code],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(3)]
   try:
    for child in children:
     out,err=child.communicate(timeout=10);self.assertEqual(0,child.returncode,err);self.assertTrue(json.loads(out)['initialized'])
    self.assertEqual(['once'],(Path(tmp)/'provisions').read_text().splitlines())
   finally:
    for child in children:
     if child.poll() is None:child.kill();child.communicate(timeout=5)
 @unittest.skipUnless(os.environ.get('CADDIE_TEST_LOCAL_PG_BIN'),'local PostgreSQL binaries not configured')
 def test_two_real_initializers_create_one_cluster_and_keep_credentials(self):
  binary=Path(os.environ['CADDIE_TEST_LOCAL_PG_BIN'])
  with tempfile.TemporaryDirectory(prefix='caddie-startup-',dir='/tmp') as tmp:
   runtime=Path(tmp)/'runtime';sock=Path(tmp)/'socket';log=Path(tmp)/'commands'
   with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
   code=f'''import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,{str(SOURCE.parent)!r})
import local_postgres as p
p.RUNTIME=Path({str(runtime)!r});p.SOCKET=Path({str(sock)!r})
original=p.run
def run(args,**kw):
 with Path({str(log)!r}).open('a') as f:f.write(Path(args[0]).name+'\\n')
 return original(args,**kw)
p.run=run
result=p.start({port})
print(hashlib.sha256(result['application_url'].encode()).hexdigest())
'''
   env=dict(os.environ,CADDIE_PG_BIN=str(binary))
   env['PYTHONPATH']=os.pathsep.join([str(ROOT/'.runtime/python'),os.environ.get('PYTHONPATH','')])
   children=[subprocess.Popen([sys.executable,'-B','-c',code],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
   try:
    outputs=[]
    for child in children:
     out,err=child.communicate(timeout=40);self.assertEqual(0,child.returncode,err);outputs.append(out.strip())
    self.assertEqual(outputs[0],outputs[1]);self.assertTrue(json.loads((runtime/'postgres.json').read_text())['initialized'])
    self.assertEqual(1,log.read_text().splitlines().count('initdb'));self.assertEqual(1,log.read_text().splitlines().count('pg_ctl'))
   finally:
    for child in children:
     if child.poll() is None:child.kill();child.communicate(timeout=5)
    if (runtime/'postgres/postmaster.pid').exists():subprocess.run([str(binary/'pg_ctl'),'-D',str(runtime/'postgres'),'-m','fast','-w','stop'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
