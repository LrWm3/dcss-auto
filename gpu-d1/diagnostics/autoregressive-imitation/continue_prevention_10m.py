"""Resume lower-LR and frozen-first-layer controls through 5M/10M checkpoints."""
import fcntl,json,pathlib,subprocess,sys,time
import torch
import episode_credit as ec
import run_ring_ablations as runner
ROOT=ec.ROOT
SOURCE=ROOT/'learning-runs/autoregressive-update-prevention'
SUITE=ROOT/'learning-runs/autoregressive-update-prevention-10m'
IDS=['lr10-seed0','frozen-first-layer-seed0']

def main():
 torch.set_num_threads(1);SUITE.mkdir(parents=True,exist_ok=True);store=runner.Store(SUITE,2*runner.GIB,10*runner.GIB)
 with (SUITE/'.pipeline.lock').open('a') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);start=time.monotonic()
  try:
   old=json.loads((SOURCE/'manifest.json').read_text());worker=pathlib.Path(__file__).with_name('update_prevention.py')
   manifest=dict(format='autoregressive-update-prevention-10m',corpus=old['corpus'],jobs=[],continuations={},sources={str(p):runner.digest(p) for p in [pathlib.Path(__file__),worker,runner.ROOT/'scripts/run_ring_ablations.py',runner.ROOT/'scripts/tactical_models.py']})
   for ident in IDS:
    original=next(j for j in old['jobs'] if j['id']==ident);cp=SOURCE/'runs'/ident/'latest.pt';saved=torch.load(cp,map_location='cpu',weights_only=False)
    assert saved['job']==original and saved['decisions']==1000448
    job=dict(original,steps=10000000,evaluation_steps=[5000000,10000000],source_train_seconds=saved['train_seconds'])
    assert job['entropy']==0 and job['turn_reward']==-.00001 and job['kill_milli']==0
    assert job['lr']==(.00003 if ident=='lr10-seed0' else .0003)
    manifest['jobs'].append(job);manifest['continuations'][ident]=dict(checkpoint=str(cp),sha256=runner.digest(cp),source_decisions=saved['decisions'],source_train_seconds=saved['train_seconds'])
    dest=pathlib.Path('runs')/ident/'latest.pt'
    if not (SUITE/dest).exists():
     saved['job']=job;store.atomic(dest,lambda f:torch.save(saved,f),256*runner.MIB)
    del saved
   if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==manifest,'Continuation/source drift'
   else:store.json('manifest.json',manifest)
   results={}
   for job in manifest['jobs']:
    folder=SUITE/'runs'/job['id'];store.json('status.json',dict(status='training',job=job['id'],started_at=time.time()));print('Continuing',job['id'],flush=True)
    if not (folder/'result.json').exists():
     cmd=[sys.executable,str(worker),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','2','--min-free-gb','10']
     if job.get('freeze_body'):cmd+=['--freeze-body'] # Worker freezes only body[0].
     subprocess.run(cmd,check=True)
    result=json.loads((folder/'result.json').read_text());assert result['decisions']==10000384
    curve=json.loads((folder/'curve.json').read_text());assert [r['decisions'] for r in curve][-2:]==[5000192,10000384]
    if job.get('freeze_body'):
     initial=torch.load(job['initial_model'],map_location='cpu',weights_only=False)['model']
     for step in [5000192,10000384]:
      state=torch.load(folder/'snapshots'/f'{step:012d}.pt',map_location='cpu',weights_only=False)['model']
      assert all(torch.equal(state[k],v) for k,v in initial.items() if k.startswith('body.0.'))
    results[job['id']]=dict(ppo=result,evaluations=curve)
    (ROOT/'results/autoregressive-update-prevention-10m.json').write_text(json.dumps(dict(results=results,wall_seconds=time.monotonic()-start),indent=2)+'\n')
   store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Both 10M continuations complete',flush=True)
  except Exception as exc:
   store.json('status.json',dict(status='failed',failure=f'{type(exc).__name__}: {exc}',wall_seconds=time.monotonic()-start));raise
if __name__=='__main__':main()
