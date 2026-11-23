"""Atomic custom-format PostgreSQL backup; credentials stay out of argv/logs."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path

def backup(destination):
 url=os.environ.get('CADDIE_DATABASE_URL','')
 if not url.startswith(('postgresql://','postgres://')):raise ValueError('PostgreSQL URL required')
 binary=shutil.which('pg_dump')
 if not binary:raise RuntimeError('install matching PostgreSQL client tools')
 destination=Path(destination).resolve()
 if destination.exists():raise ValueError('destination already exists')
 destination.parent.mkdir(parents=True,exist_ok=True)
 fd,name=tempfile.mkstemp(prefix='.caddie-backup-',dir=destination.parent);os.close(fd)
 try:
  from psycopg.conninfo import conninfo_to_dict
  fields=conninfo_to_dict(url)
  mapping={'dbname':'PGDATABASE','user':'PGUSER','password':'PGPASSWORD','host':'PGHOST','hostaddr':'PGHOSTADDR','port':'PGPORT','sslmode':'PGSSLMODE','sslrootcert':'PGSSLROOTCERT','sslcert':'PGSSLCERT','sslkey':'PGSSLKEY','sslpassword':'PGSSLPASSWORD','connect_timeout':'PGCONNECT_TIMEOUT','application_name':'PGAPPNAME','options':'PGOPTIONS','target_session_attrs':'PGTARGETSESSIONATTRS','channel_binding':'PGCHANNELBINDING','service':'PGSERVICE','passfile':'PGPASSFILE','requirepeer':'PGREQUIREPEER','gssencmode':'PGGSSENCMODE'}
  if set(fields)-set(mapping):raise ValueError('unsupported backup connection options')
  env={k:v for k,v in os.environ.items() if not k.startswith('PG')}
  env.update({mapping[k]:v for k,v in fields.items()})
  subprocess.run([binary,'--format=custom','--no-owner','--file',name],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=300)
  with open(name,'rb') as source:digest=hashlib.file_digest(source,'sha256').hexdigest()
  # Hard link prevents accidentally replacing a backup produced by another process.
  os.link(name,destination)
  print(json.dumps({'file':str(destination),'sha256':digest,'bytes':destination.stat().st_size}))
 finally:Path(name).unlink(missing_ok=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('destination');args=parser.parse_args();backup(args.destination)
