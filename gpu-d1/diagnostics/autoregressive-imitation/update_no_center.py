"""Queue a no-advantage-centering control behind the prevention screen."""
import json,pathlib,subprocess,sys,time
import episode_credit as ec
import run_ring_ablations as runner
ROOT=ec.ROOT
while True:
 p=ROOT/'learning-runs/autoregressive-update-prevention/status.json'
 if p.exists() and json.loads(p.read_text())['status']=='complete':break
 time.sleep(10)
suite=ROOT/'learning-runs/autoregressive-no-centering';suite.mkdir(exist_ok=True)
old=json.loads((ROOT/'learning-runs/autoregressive-turn-cost/manifest.json').read_text());job=dict(old['jobs'][0],id='no-centering-seed0',name='no-centering',diagnostic_no_advantage_centering=True)
store=runner.Store(suite,2*runner.GIB,10*runner.GIB);store.json('manifest.json',dict(corpus=old['corpus'],jobs=[job]));store.json('status.json',dict(status='running'));start=time.monotonic()
subprocess.run([sys.executable,str(runner.ROOT/'scripts/run_ring_ablations.py'),'--worker',job['id'],'--output',str(suite),'--max-disk-gb','2','--min-free-gb','10'],check=True)
folder=suite/'runs'/job['id'];output=dict(ppo=json.loads((folder/'result.json').read_text()),evaluations=json.loads((folder/'curve.json').read_text()))
(ROOT/'results/autoregressive-no-centering.json').write_text(json.dumps(output,indent=2)+'\n');store.json('status.json',dict(status='complete',seconds=time.monotonic()-start))
