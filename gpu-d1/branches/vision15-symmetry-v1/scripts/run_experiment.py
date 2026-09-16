"""Run two 30M D4-camera policies, then the existing tactical evaluation suite."""
import json
import os
import pathlib
import subprocess
import sys
import time
import torch
import run_ring_ablations as runner

def main():
    start=time.monotonic();root=runner.ROOT.parents[1]
    suite=root/'learning-runs/vision15-symmetry-30m'
    reference=json.loads((root/'learning-runs/vision15-clumps-30m/manifest.json').read_text())
    corpus=pathlib.Path(reference['corpus'])
    assert runner.corpus_manifest(corpus)==reference['maps']
    assert (runner.ROOT/'src/learn.cu').read_bytes()==(root/'branches/vision15-clumps-v1/src/learn.cu').read_bytes()
    assert (runner.ROOT/'src/sim.h').read_bytes()==(root/'branches/vision15-clumps-v1/src/sim.h').read_bytes()
    def run(path,*args,env=None):
        subprocess.run([sys.executable,str(path),*map(str,args)],check=True,env=env)
    run(runner.ROOT/'scripts/preflight.py')
    run(runner.ROOT/'scripts/run_ring_ablations.py','--output',suite,'--corpus',corpus,'--steps',30000000,'--seeds',0)
    actual=json.loads((suite/'manifest.json').read_text());assert actual['maps']==reference['maps']
    original=torch.load(root/'learning-runs/vision15-seen-death4-10m/runs/tiles_seen_death4-seed0/snapshots/000000000000.pt',weights_only=False,map_location='cpu')['model']
    paths={}
    for key,name in [('ordinary','ordinary_d4'),('mixed','clumps_d4')]:
        folder=suite/'runs'/f'{name}-seed0'
        initial=torch.load(folder/'snapshots/000000000000.pt',weights_only=False,map_location='cpu')['model']
        assert all(torch.equal(v,original[k]) for k,v in initial.items()),name
        paths[key]=str(folder/'snapshots/000030015488.pt')
        assert pathlib.Path(paths[key]).is_file()
    config=suite/'diagnostic-models.json';config.write_text(json.dumps(dict(paths,result_prefix='d4-'),indent=2)+'\n')
    env=os.environ|{'DCSS_DIAGNOSTIC_MODELS':str(config)}
    for name,args in [('hallway',[]),('hallway-six',[]),('diagonal-pocket',[]),('distant-pocket',['--distance','4']),('distant-pocket',['--distance','6'])]:
        run(root/'diagnostics'/name/'run.py',*args,env=env)
    for distance in [4,6]:
        for mirror in [0,1]:
            run(root/'diagnostics/pocket-symmetry/run.py','--distance',distance,'--mirror',mirror,env=env)
    run(root/'diagnostics/pocket-action/run.py',env=env)
    run(runner.ROOT/'scripts/summarize.py')
    report=dict(manifest=actual,initial_weights_exact=True,native_sources_exact=True,wall_seconds=time.monotonic()-start,diagnostic_models=paths)
    (root/'results/vision15-symmetry-run.json').write_text(json.dumps(report,separators=(',',':'))+'\n')
    print('Experiment complete',report['wall_seconds'],flush=True)
if __name__=='__main__':main()
