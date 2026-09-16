"""Queue unaugmented seeds 1/2 behind D4 pipeline; run identical tactical probes."""
import json
import os
import pathlib
import subprocess
import sys
import time
import torch
import run_ring_ablations as runner

ROOT=runner.ROOT.parents[1]

def proc_start(pid):
    try:
        fields=pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
        return fields[19] if fields[0]!='Z' else None
    except FileNotFoundError:return None

def main():
    queue_start=time.monotonic()
    upstream=json.loads((ROOT/'learning-runs/vision15-symmetry-pipeline.json').read_text())
    pid=upstream['pid'];identity=proc_start(pid)
    print(json.dumps(dict(status='queued',waiting_for_pid=pid,variants=['ordinary','clumps_third'],seeds=[1,2],decisions_each=30000000)),flush=True)
    while identity is not None and proc_start(pid)==identity:time.sleep(15)
    # Fail visibly rather than silently bypassing an incomplete upstream experiment.
    if not (ROOT/'results/vision15-symmetry-run.json').exists():
        raise RuntimeError('Upstream D4 pipeline ended without completion marker; inspect its log before retrying queue')
    start=time.monotonic();suite=ROOT/'learning-runs/vision15-direction-seeds-30m'
    reference=json.loads((ROOT/'learning-runs/vision15-clumps-30m/manifest.json').read_text())
    corpus=pathlib.Path(reference['corpus'])
    assert runner.corpus_manifest(corpus)==reference['maps']
    for name in ['learn.cu','sim.h']:
        assert (runner.ROOT/'src'/name).read_bytes()==(ROOT/'branches/vision15-clumps-v1/src'/name).read_bytes()
    def run(path,*args,env=None):subprocess.run([sys.executable,str(path),*map(str,args)],check=True,env=env)
    run(runner.ROOT/'scripts/run_ring_ablations.py','--output',suite,'--corpus',corpus,'--steps',30000000,'--seeds','1,2')
    result={'seeds':[1,2],'augmentation':False,'training':{},'diagnostics':{},'native_sources_exact':True}
    prior_initial=torch.load(ROOT/'learning-runs/vision15-clumps-30m/runs/clumps_third-seed0/snapshots/000000000000.pt',map_location='cpu',weights_only=False)['model']
    for seed in [1,2]:
        paths={};initials=[]
        for key,name in [('ordinary','ordinary'),('mixed','clumps_third')]:
            folder=suite/'runs'/f'{name}-seed{seed}'
            initial=torch.load(folder/'snapshots/000000000000.pt',map_location='cpu',weights_only=False)['model'];initials.append(initial)
            assert any(not torch.equal(v,prior_initial[k]) for k,v in initial.items()),'Training seeds did not change initialization'
            paths[key]=str(folder/'snapshots/000030015488.pt')
            result['training'][f'{name}-seed{seed}']=json.loads((folder/'result.json').read_text())
        assert all(torch.equal(v,initials[1][k]) for k,v in initials[0].items()),'Paired initialization differs'
        prefix=f'seed{seed}-noaug-'
        config=suite/f'diagnostic-models-seed{seed}.json';config.write_text(json.dumps(dict(paths,result_prefix=prefix),indent=2)+'\n')
        env=os.environ|{'DCSS_DIAGNOSTIC_MODELS':str(config)}
        tasks=[('hallway',[],'hallway-retreat.json'),('hallway-six',[],'hallway-six-retreat.json'),('diagonal-pocket',[],'diagonal-pocket-retreat.json')]
        tasks += [('distant-pocket',['--distance',str(d)],f'distant-pocket-{d}-retreat.json') for d in [4,6]]
        tasks += [('pocket-symmetry',['--distance',str(d),'--mirror',str(m)],f'pocket-symmetry-{d}-mirror{m}.json') for d in [4,6] for m in [0,1]]
        for folder,args,output in tasks:
            run(ROOT/'diagnostics'/folder/'run.py',*args,env=env)
            data=json.loads((ROOT/'results'/(prefix+output)).read_text())
            baseline=json.loads((ROOT/'results'/output).read_text())
            for arm in ['hold_fight','retreat_fight']:
                if arm in data['arms']:assert data['arms'][arm]==baseline['arms'][arm],(seed,output,arm,'control drift')
            # Keep rotation arrays, rather than only pooling away directional failures.
            result['diagnostics'][prefix+output]={arm:dict(win=v['win'],unresolved=v['unresolved'],**{k:vv for k,vv in v.items() if k.endswith('_contact_turns') or k.endswith('_wait_turns')}) for arm,v in data['arms'].items()}
        run(ROOT/'diagnostics/pocket-action/run.py',env=env)
        result['diagnostics'][prefix+'pocket-static-actions.json']=json.loads((ROOT/'results'/(prefix+'pocket-static-actions.json')).read_text())
    result.update(paired_initializations_exact=True,initializations_differ_from_seed0=True,scripted_controls_exact=True,queue_seconds=start-queue_start,wall_seconds=time.monotonic()-start)
    (ROOT/'results/vision15-direction-seeds-run.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
    print('Seed comparison complete',result['wall_seconds'],flush=True)
if __name__=='__main__':main()
