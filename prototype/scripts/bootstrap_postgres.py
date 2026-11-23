"""Provision the PostgreSQL schema explicitly; no legacy data migration."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/api'))
from database import require_url,bootstrap_schema
if __name__=='__main__':
 bootstrap_schema(require_url());print('PostgreSQL schema initialized; no old data imported.')
