"""Freeze a deterministic core dependency closure before changing CORE_VERSION.
No overwrite, deletion, network or dynamic runtime loading. Register the frozen version explicitly.
"""
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'shared/core'
ENTRIES=('protocol.ts','roundEngine.ts','dialogue.ts','strategy.ts','offlineSetup.ts','webJourney.ts')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(folder):
 manifest=json.loads((folder/'manifest.json').read_text());files=manifest['files']
 if {p.name for p in folder.glob('*.ts')}!=set(files):raise ValueError('release file set changed')
 for name,expected in files.items():
  path=folder/name
  if path.parent!=folder or digest(path)!=expected:raise ValueError('frozen source changed: '+name)
  for target in re.findall(r"from ['\"](.+?)['\"]",path.read_text()):
   if not target.startswith('./') or target[2:] not in files:raise ValueError('release dependency escapes closure: '+target)
 return manifest

def freeze():
 protocol=(ROOT/'protocol.ts').read_text();version=re.search(r"CORE_VERSION='([^']+)'",protocol)[1];dataset=re.search(r"CORE_DATASET='([^']+)'",protocol)[1]
 folder=ROOT/'releases'/version
 if folder.exists():raise ValueError('release already exists; refusing overwrite')
 pending=list(ENTRIES);files={}
 while pending:
  name=pending.pop()
  if name in files:continue
  if '/' in name or not name.endswith('.ts'):raise ValueError('unsupported source dependency')
  data=(ROOT/name).read_bytes();files[name]=data
  for target in re.findall(r"from ['\"](.+?)['\"]",data.decode()):
   if not target.startswith('./'):raise ValueError('nonlocal dependency')
   pending.append(target[2:])
 folder.mkdir(parents=True)
 for name,data in files.items():(folder/name).write_bytes(data)
 manifest=dict(core_version=version,dataset=dataset,files={name:digest(folder/name) for name in sorted(files)})
 (folder/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');verify(folder)
 print('Frozen '+version+'; add an explicit static entry to runtime.ts before the next release.')
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--verify',action='store_true');args=parser.parse_args()
 if args.verify:
  for folder in sorted((ROOT/'releases').iterdir()):
   if folder.is_dir():verify(folder)
  print('Frozen release checksums and dependencies verified')
 else:freeze()
