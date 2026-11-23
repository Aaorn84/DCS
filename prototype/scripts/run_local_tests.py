"""Run regression suites against disposable PostgreSQL schemas, never the app DB."""
import argparse,os,subprocess,sys
from pathlib import Path
from local_postgres import start,prepare_imports,binaries,ROOT
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--suite',choices=['all','api','business','client','benchmark'],default='all');args=parser.parse_args()
 prepare_imports();settings=start()
 env=dict(os.environ,CADDIE_TEST_POSTGRES_URL=settings['test_url'],PYTHONDONTWRITEBYTECODE='1',CADDIE_TEST_PYTHON=sys.executable)
 env['CADDIE_TEST_LOCAL_PG_BIN']=str(binaries())
 env['PYTHONPATH']=os.pathsep.join([str(ROOT/'.runtime/python'),str(ROOT/'prototype'),os.environ.get('PYTHONPATH','')])
 commands=[]
 if args.suite in ('all','business'):commands.append([sys.executable,'-B','-m','unittest','discover','-s','skills/golf-caddie/tests','-p','test_*.py'])
 if args.suite in ('all','api'):commands.append([sys.executable,'-B','-m','unittest','discover','-s','prototype/tests','-p','test_*.py'])
 if args.suite in ('all','client'):
  from shared_core import _node
  commands.append([_node(),'--experimental-transform-types','--test',*[str(p.relative_to(ROOT)) for p in sorted((ROOT/'prototype/tests').glob('*.test.mjs'))]])
 if args.suite=='benchmark':commands.append([sys.executable,'-B','prototype/scripts/benchmark_web_core.py'])
 for command in commands:
  result=subprocess.run(command,cwd=ROOT,env=env)
  if result.returncode:sys.exit(result.returncode)
