"""Paired fresh seed-0 runs: primitive wait versus optional rest-to-full."""
import fcntl,json,pathlib,subprocess,sys,time
from assets import ROOT,ASSETS
import run_ring_ablations as runner
SUITE=ROOT/'learning-runs/vision15-centered-map'
def plan():
 old=json.loads((ROOT/'learning-runs/vision15-tactical-next/manifest.json').read_text());base=next(j for j in old['jobs'] if j['id']=='d4_exact_clumped-seed0')
 for key in ['source_suite','source_job','tactical_library','tactical_corpus']:base.pop(key,None)
 jobs=[]
 for rest in [1]:
  name='rest' if rest else 'wait'
  jobs.append(dict(base,name=name,id=f'{name}-seed0',steps=10000000,rest_action=rest,sleep_status="global_signed",architecture="centered_map",terrain_los=0,global_enemies=1,monster_wake_los=False,frontier=False,route_cue=False,no_ring=True,explore_milli=0,gradient_chunk=512,curriculum=False,checkpoint_every=1000000,train_library=str(ASSETS/f'rest{rest}-clump1.so'),eval_library=str(ASSETS/f'rest{rest}-clump0.so'),budget_unit='game_turns',rest_rule='no_awake_enemy_within_chebyshev_7'))
 return dict(format='centered-map-v1',jobs=jobs,corpus=old['corpus'],maps=old['maps'],sources={str(p.relative_to(runner.ROOT)):runner.digest(p) for sub in ['scripts','src'] for p in sorted((runner.ROOT/sub).iterdir()) if p.suffix in ['.py','.cu','.h']},libraries={p.name:runner.digest(p) for p in sorted(ASSETS.glob('*.so'))})
def main():
 SUITE.mkdir(parents=True,exist_ok=True);store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB);start=time.monotonic()
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);m=plan();path=SUITE/'manifest.json'
  if path.exists():assert json.loads(path.read_text())==m,'Source/plan drift'
  else:store.json('manifest.json',m)
  for j in m['jobs']:
   if (SUITE/'runs'/j['id']/'result.json').exists():continue
   store.json('status.json',dict(status='training',job=j['id'],started_at=time.time()));print('Starting',j['id'],flush=True)
   subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),'--worker',j['id'],'--output',str(SUITE),'--max-disk-gb','2','--min-free-gb','10'],check=True)
  results=[json.loads((SUITE/'runs'/j['id']/'result.json').read_text()) for j in m['jobs']]
  (ROOT/'results/centered-map-training-summary.json').write_text(json.dumps(dict(jobs=results,wall_seconds=time.monotonic()-start),separators=(',',':'))+'\n')
  store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Rest comparison complete',flush=True)
if __name__=='__main__':main()
