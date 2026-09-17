"""Short, matched ordinary-floor PPO continuations with optional corrective labels."""
import fcntl,json,pathlib,subprocess,sys,time
import torch
import run_ring_ablations as runner
from ordinary_eval import ROOT,SOURCE
HERE=pathlib.Path(__file__).resolve().parent
SUITE=ROOT/'learning-runs/autoregressive-ordinary'

def main():
    torch.set_num_threads(1);SUITE.mkdir(parents=True,exist_ok=True)
    with (SUITE/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);start=time.monotonic();store=runner.Store(SUITE,4*runner.GIB,10*runner.GIB)
        saved=torch.load(SOURCE,map_location='cpu',weights_only=False);base=saved['decisions'];assert base==35000320
        template={k:v for k,v in saved['job'].items() if not k.startswith(('tactical_','practice_','target_eval_'))}
        template.update(curriculum=False,steps=36000768,evaluation_steps=[35500544,36000768],source_train_seconds=saved['train_seconds'])
        manifest=dict(corpus=json.loads((ROOT/'learning-runs/autoregressive-survival/manifest.json').read_text())['corpus'],source_checkpoint=str(SOURCE),source_sha256=runner.digest(SOURCE),source_decisions=base,jobs=[],sources={str(p):runner.digest(p) for p in HERE.glob('*.py')})
        for name,scope,weight in [('control','none',0.),('wait','wait',.1),('teacher','all',.3)]:
            job=dict(template,id=name+'-seed0',name=name,correction_scope=scope,correction_weight=weight);manifest['jobs'].append(job)
            path=pathlib.Path('runs')/job['id']/'latest.pt'
            if not (SUITE/path).exists():
                c=dict(saved,job=job,history=[],best=None,best_score=(-1.,-1.));old=c.pop('curriculum_state');c['env_obs']=old['raw_obs'];c['env_mask']=old['raw_mask']
                store.atomic(path,lambda f:torch.save(c,f),256*runner.MIB)
        if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==manifest,'Source/configuration drift'
        else:store.json('manifest.json',manifest)
        del saved
        results={}
        try:
            for i,job in enumerate(manifest['jobs']):
                store.json('status.json',dict(status='training',job=job['id'],queued=[x['id'] for x in manifest['jobs'][i+1:]]));print('Starting',job['id'],flush=True)
                folder=SUITE/'runs'/job['id']
                if not (folder/'result.json').exists():subprocess.run([sys.executable,str(HERE/'run_ring_ablations.py'),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','4','--min-free-gb','10'],check=True)
                r=json.loads((folder/'result.json').read_text());assert r['decisions']==36000768
                results[job['id']]=dict(additional_train_seconds=r['additional_train_seconds'],evaluations=json.loads((folder/'curve.json').read_text()))
                (ROOT/'results/autoregressive-ordinary-screen.json').write_text(json.dumps(dict(source_decisions=base,results=results,wall_seconds=time.monotonic()-start),indent=2,allow_nan=False)+'\n')
            store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Ordinary screen complete',flush=True)
        except Exception as exc:
            store.json('status.json',dict(status='failed',failure=str(exc)));raise

if __name__=='__main__':main()
