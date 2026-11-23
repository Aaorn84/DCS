"""Launch the demo against the local PostgreSQL runtime, not a file database."""
import os,runpy,sys
from pathlib import Path
from local_postgres import start,ROOT
settings=start();os.environ['CADDIE_DATABASE_URL']=settings['application_url']
sys.argv=[str(ROOT/'demo-local/serve.py'),*sys.argv[1:]]
runpy.run_path(str(ROOT/'demo-local/serve.py'),run_name='__main__')
