"""Disposable schema on an explicitly configured PostgreSQL TEST database."""
import os,uuid
from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode,quote
import psycopg
from psycopg import sql

class TestDatabase:
 def __init__(self):
  base=os.environ.get('CADDIE_TEST_POSTGRES_URL','')
  if not base.startswith(('postgresql://','postgres://')):raise RuntimeError('CADDIE_TEST_POSTGRES_URL must point to a disposable PostgreSQL database')
  self.base=base;self.schema='test_'+uuid.uuid4().hex;self.closed=False
  with psycopg.connect(base,autocommit=True) as db:db.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
  p=urlsplit(base);options=dict(parse_qsl(p.query));options['options']='-c search_path='+self.schema
  self.url=urlunsplit((p.scheme,p.netloc,p.path,urlencode(options,quote_via=quote),p.fragment))
  from database import bootstrap_schema
  try:bootstrap_schema(self.url)
  except Exception:self.cleanup();raise
 def cleanup(self):
  if self.closed:return
  self.closed=True
  from database import close_pools
  close_pools(self.url)
  with psycopg.connect(self.base,autocommit=True) as db:db.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)))
 def __enter__(self):return self
 def __exit__(self,*args):self.cleanup()
