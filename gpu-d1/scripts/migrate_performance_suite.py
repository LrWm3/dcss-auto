"""Fork a stopped suite into fast mode without changing its learning state.

Only performance metadata changes; original outputs remain untouched.
"""
import argparse,importlib,json,pathlib,sys
import torch

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--runner-root',type=pathlib.Path,required=True)
ap.add_argument('--source',type=pathlib.Path,required=True)
ap.add_argument('--output',type=pathlib.Path,required=True)
a=ap.parse_args();source=a.source.resolve();target=a.output.resolve()
if target.exists():raise RuntimeError(f'Refusing to overwrite {target}')
# An active coordinator holds this lock throughout the suite.
import fcntl
with (source/'.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 sys.path.insert(0,str(a.runner_root.resolve()/'scripts'))
 runner=importlib.import_module('run_ring_ablations')
 original=json.loads((source/'manifest.json').read_text())
 manifest=json.loads(json.dumps(original))
 manifest['sources']={p:runner.digest(runner.ROOT/p) for p in runner.SOURCE_FILES}
 records=[];payloads=[]
 for job,previous in zip(manifest['jobs'],original['jobs']):
  folder=pathlib.Path('runs')/job['id'];path=source/folder/'latest.pt'
  saved=torch.load(path,map_location='cpu',weights_only=False)
  assert saved['job']==previous
  if saved['decisions']>=job['steps']:raise RuntimeError(f'{job["id"]} is already finished')
  job['performance']='fast';saved['job']=dict(job)
  if saved.get('best') is not None:saved['best']['job']=dict(job)
  records.append(dict(job=job['id'],source_checkpoint=str(path),sha256=runner.digest(path),decisions=saved['decisions'],train_seconds=saved['train_seconds']))
  payloads.append((folder,saved))
 target.mkdir(parents=True)
 (target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 (target/'source-manifest.json').write_text(json.dumps(original,indent=2)+'\n')
 (target/'performance-migration.json').write_text(json.dumps(dict(source=str(source),runner_root=str(runner.ROOT),checkpoints=records,changes='fast route BFS, launch size, inactive evaluation worlds; learning state and ogre counters preserved'),indent=2)+'\n')
 for folder,saved in payloads:
  (target/folder).mkdir(parents=True)
  torch.save(saved,target/folder/'latest.pt')
  (target/folder/'curve.json').write_text(json.dumps(saved['history'],indent=2)+'\n')
 print(json.dumps(records,indent=2));print('Prepared:',target)
