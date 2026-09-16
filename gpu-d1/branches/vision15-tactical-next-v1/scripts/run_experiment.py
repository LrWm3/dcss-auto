"""Persistent sequential queue: paired continuations, curriculum, architecture screens."""
import fcntl
import json
import pathlib
import subprocess
import sys
import time
from assets import ROOT,ASSETS
from prepare import SUITE,plan,initialize,source
import run_ring_ablations as runner

def main():
    start=time.monotonic();SUITE.mkdir(parents=True,exist_ok=True);store=runner.Store(SUITE,4*runner.GIB,10*runner.GIB)
    with (SUITE/'.pipeline.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=plan();path=SUITE/'manifest.json'
        if path.exists():assert json.loads(path.read_text())==manifest,'Source/plan drift; use explicit new suite'
        else:store.json('manifest.json',manifest)
        def run(script,*args):subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name(script)),*map(str,args)],check=True)
        # Frozen held-out probes against the six old baselines use the identical bank.
        for seed in [0,1,2]:
            for placement in ['ordinary','clumped']:
                oldsuite,oldname=source(seed,placement);output=ROOT/'results'/f'tactical-next-baseline-{placement}-seed{seed}-extra.json'
                if not output.exists():run('evaluate_extra.py',oldsuite/'runs'/oldname/'snapshots/000030015488.pt',output)
        for job in manifest['jobs']:
            output=SUITE/'runs'/job['id']/'result.json'
            if not output.exists():
                initialize(store,job)
                store.json('status.json',dict(status='training',job=job['id'],started_at=time.time()))
                print('Starting',job['id'],flush=True)
                run('run_ring_ablations.py','--worker',job['id'],'--output',SUITE,'--max-disk-gb',4,'--min-free-gb',10)
            # Pair evaluations after the second placement model completes.
            if job['name'].endswith('_clumped'):
                kind=job['name'].removesuffix('_clumped');seed=job['seed']
                for milestone in ([50_000_000,75_000_000,100_000_000] if kind in ['continue','targeted'] else [30_000_000]):
                    n=((milestone+32767)//32768)*32768
                    prefix=f"tactical-next-{kind.replace('_', '-')}-seed{seed}-{milestone//1000000}m-"
                    if (ROOT/'results'/f'{prefix}complete.json').exists():continue
                    store.json('status.json',dict(status='evaluation',experiment=prefix,started_at=time.time()))
                    ordinary=SUITE/'runs'/f'{kind}_ordinary-seed{seed}'/'snapshots'/f'{n:012d}.pt'
                    clumped=SUITE/'runs'/f'{kind}_clumped-seed{seed}'/'snapshots'/f'{n:012d}.pt'
                    run('evaluate_pair.py','--ordinary',ordinary,'--clumped',clumped,'--prefix',prefix)
        store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start))
        results=[json.loads((SUITE/'runs'/j['id']/'result.json').read_text()) for j in manifest['jobs']]
        (ROOT/'results/tactical-next-training-summary.json').write_text(json.dumps(dict(jobs=results,wall_seconds=time.monotonic()-start),separators=(',',':'))+'\n')
        print('Tactical follow-up queue complete',flush=True)
if __name__=='__main__':main()
