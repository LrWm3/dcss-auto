"""Three sequential, resumable 5M continuations from the same 30M checkpoint."""
import argparse,fcntl,json,pathlib,subprocess,sys,time
import torch
import run_ring_ablations as runner
from preflight import settings,SOURCE
from scenarios import ROOT,ASSETS,HERE


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--smoke',action='store_true');args=ap.parse_args()
    torch.set_num_threads(1)
    name='autoregressive-survival'+('-smoke' if args.smoke else '')
    suite=ROOT/'learning-runs'/name;suite.mkdir(parents=True,exist_ok=True)
    store=runner.Store(suite,4*runner.GIB,10*runner.GIB)
    with (suite/'.pipeline.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);start=time.monotonic()
        try:
            old,template=settings();cp=SOURCE/'runs/navigation1-seed0/latest.pt'
            saved=torch.load(cp,map_location='cpu',weights_only=False)
            assert saved['decisions']==30000128 and saved['job']==old['jobs'][0]
            base=saved['decisions'];budgets=[8192] if args.smoke else [500000,1000000,5000000]
            steps=[base+((x+511)//512)*512 for x in budgets]
            arms=[('exploration',True,5.)] if args.smoke else [('control',False,1.),('practice',True,1.),('exploration',True,5.)]
            manifest=dict(format=name,corpus=old['corpus'],source_checkpoint=str(cp),source_sha256=runner.digest(cp),source_decisions=base,jobs=[],sources={str(p):runner.digest(p) for folder in ['scripts','src'] for p in (HERE/folder).glob('*') if p.is_file()},assets={str(p):runner.digest(p) for p in ASSETS.rglob('*') if p.is_file()})
            for arm,curriculum,temperature in arms:
                job=dict(template,id=arm+'-seed0',name=arm,curriculum=curriculum,practice_temperature=temperature,steps=steps[-1],evaluation_steps=steps,source_train_seconds=saved['train_seconds'])
                if args.smoke:job.update(validation_maps=8,eval_per_map=8)
                manifest['jobs'].append(job)
                dest=pathlib.Path('runs')/job['id']/'latest.pt'
                if not (suite/dest).exists():
                    continuation=dict(saved,job=job)
                    store.atomic(dest,lambda f:torch.save(continuation,f),256*runner.MIB)
            del saved
            if (suite/'manifest.json').exists():assert json.loads((suite/'manifest.json').read_text())==manifest,'Source/configuration drift'
            else:store.json('manifest.json',manifest)
            results={}
            for j,job in enumerate(manifest['jobs']):
                folder=suite/'runs'/job['id']
                store.json('status.json',dict(status='training',job=job['id'],queued=[x['id'] for x in manifest['jobs'][j+1:]],started_at=time.time()))
                print('Starting',job['id'],'additional decisions',steps[-1]-base,flush=True)
                if not (folder/'result.json').exists():
                    subprocess.run([sys.executable,str(HERE/'scripts/run_ring_ablations.py'),'--worker',job['id'],'--output',str(suite),'--max-disk-gb','4','--min-free-gb','10'],check=True)
                result=json.loads((folder/'result.json').read_text());curve=json.loads((folder/'curve.json').read_text())
                assert result['decisions']==steps[-1]
                new=[r for r in curve if r['decisions']>base]
                assert [r['decisions'] for r in new]==steps
                if job['curriculum']:
                    count=new[-1]['curriculum_counts'];assert count[1]/(count[0]+count[1])==51/512
                results[job['id']]=dict(ppo=result,evaluations=new)
                (ROOT/'results'/f'{name}.json').write_text(json.dumps(dict(source_decisions=base,results=results,wall_seconds=time.monotonic()-start),indent=2)+'\n')
            store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Survival comparison complete',flush=True)
        except Exception as exc:
            store.json('status.json',dict(status='failed',failure=f'{type(exc).__name__}: {exc}',wall_seconds=time.monotonic()-start));raise

if __name__=='__main__':main()
