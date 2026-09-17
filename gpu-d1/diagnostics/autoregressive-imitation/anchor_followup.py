"""Replicate a selected anchor strength, or test a specified new strength."""
import argparse,fcntl,json,pathlib,subprocess,sys,time
import episode_credit as ec
import run_ring_ablations as runner
ROOT=ec.ROOT

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--kind',choices=['feature','policy'],required=True);ap.add_argument('--weight',type=float,required=True);ap.add_argument('--seeds',default='1,2');ap.add_argument('--name',required=True);ap.add_argument('--steps',type=int,default=10000000);args=ap.parse_args()
    assert args.weight>0
    suite=ROOT/'learning-runs'/args.name;suite.mkdir(parents=True,exist_ok=True);store=runner.Store(suite,3*runner.GIB,10*runner.GIB)
    with (suite/'.pipeline.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=json.loads((ROOT/'learning-runs/autoregressive-anchor-screen/manifest.json').read_text());base=old['jobs'][0]
        jobs=[dict(base,id=f'{args.kind}{args.weight:g}-seed{seed}',name=f'{args.kind}{args.weight:g}',seed=seed,steps=args.steps,anchor_kind=args.kind,anchor_weight=args.weight) for seed in map(int,args.seeds.split(','))]
        manifest=dict(corpus=old['corpus'],jobs=jobs,sources={str(p):runner.digest(p) for p in [pathlib.Path(__file__),pathlib.Path(runner.__file__),pathlib.Path(runner.__file__).with_name('imitation_anchor.py')]})
        if (suite/'manifest.json').exists():assert json.loads((suite/'manifest.json').read_text())==manifest
        else:store.json('manifest.json',manifest)
        start=time.monotonic();result={}
        for job in jobs:
            store.json('status.json',dict(status='training',job=job['id']));folder=suite/'runs'/job['id']
            if not (folder/'result.json').exists():subprocess.run([sys.executable,str(pathlib.Path(runner.__file__)),'--worker',job['id'],'--output',str(suite),'--max-disk-gb','3','--min-free-gb','10'],check=True)
            result[job['id']]=dict(ppo=json.loads((folder/'result.json').read_text()),evaluations=json.loads((folder/'curve.json').read_text()))
            (ROOT/'results'/f'{args.name}.json').write_text(json.dumps(dict(results=result,wall_seconds=time.monotonic()-start),indent=2)+'\n')
        store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start))
if __name__=='__main__':main()
