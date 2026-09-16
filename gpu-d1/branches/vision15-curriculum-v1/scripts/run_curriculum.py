"""Replay 512-turn training to 2M, preserve training state, then use 2048 turns."""
import argparse
import fcntl
import json
import pathlib
import shutil
import subprocess
import sys

import torch

import run_ring_ablations as runner


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stage1',type=pathlib.Path,required=True)
    ap.add_argument('--stage2',type=pathlib.Path,required=True)
    ap.add_argument('--results',type=pathlib.Path,required=True)
    args=ap.parse_args()
    root=runner.ROOT.parents[1]
    early=root/'branches/vision15-learning-curve-v1/scripts/run_ring_ablations.py'
    subprocess.run([sys.executable,str(early),'--output',str(args.stage1),'--steps','2000000',
                    '--seeds','0','--variants','vision15_no_travel'],check=True)
    stage1=args.stage1.resolve();stage2=args.stage2.resolve()
    assert stage1!=stage2
    job_id='vision15_no_travel-seed0'
    source=stage1/'runs'/job_id/'latest.pt'
    reference=root/'learning-runs/vision15-no-travel-early-10m/runs'/job_id/'snapshots/000002031616.pt'
    saved=torch.load(source,map_location='cpu',weights_only=False)
    original=torch.load(reference,map_location='cpu',weights_only=False)
    assert saved['decisions']==original['decisions']==2_031_616
    assert saved['job']['turn_limit']==512
    assert all(torch.equal(saved['model'][k],v) for k,v in original['model'].items())
    print('Stage 1 weights exactly match the original 2,031,616-decision checkpoint.',flush=True)
    sources={p:runner.digest(runner.ROOT/p) for p in runner.SOURCE_FILES}
    sources['scripts/run_curriculum.py']=runner.digest(pathlib.Path(__file__))
    stage2.mkdir(parents=True,exist_ok=True)
    store=runner.Store(stage2,2*runner.GIB,5*runner.GIB)
    with (stage2/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if not (stage2/'manifest.json').exists():
            assert not any(p.name!='.lock' for p in stage2.iterdir()), 'Use a fresh output after incomplete preparation'
            source_manifest=json.loads((stage1/'manifest.json').read_text())
            compiled_suite=root/'learning-runs/vision15-no-travel-train2048-10m'
            compiled_manifest=json.loads((compiled_suite/'manifest.json').read_text())
            assert source_manifest['maps']==compiled_manifest['maps']
            assert runner.corpus_manifest(pathlib.Path(source_manifest['corpus']))==source_manifest['maps']
            for p in runner.SOURCE_FILES:
                if p!='scripts/run_ring_ablations.py':
                    assert sources[p]==compiled_manifest['sources'][p],p
            old_job=saved['job'].copy()
            job=dict(old_job,steps=10_000_000,turn_limit=2048,
                     curriculum_switch_decisions=2_031_616)
            native_job=compiled_manifest['jobs'][0]
            assert {k:v for k,v in job.items() if k!='curriculum_switch_decisions'}==native_job
            provenance=dict(source_checkpoint_sha256=runner.digest(source),
                            original_compact_sha256=runner.digest(reference),
                            model_weights_match=True,switch_decisions=saved['decisions'],
                            stage1_train_seconds=saved['train_seconds'],old_job=old_job,
                            state_transfer='weights, optimizer, live worlds, masks, work totals and RNG preserved; time observation divided by four')
            saved['job']=job
            saved['env_obs'][:,651]/=4
            # Validation must start fresh under the new deadline; the runner
            # evaluates an empty history immediately upon resuming this state.
            saved['history']=[];saved['best']=None;saved['best_score']=(-1.,-1.)
            store.atomic(pathlib.Path('runs')/job_id/'latest.pt',lambda f:torch.save(saved,f),128*runner.MIB)
            key=runner.library_key(job)
            (stage2/'build').mkdir()
            for suffix in ['.so','.sha256']:
                shutil.copy2(compiled_suite/'build'/(key+suffix),stage2/'build'/(key+suffix))
            assert runner.digest(stage2/'build'/(key+'.so'))==(stage2/'build'/(key+'.sha256')).read_text().strip()
            store.json('continuation.json',provenance)
            store.json('manifest.json',dict(source_manifest,jobs=[job],sources=sources))
        manifest=json.loads((stage2/'manifest.json').read_text())
        assert manifest['sources']==sources
        if not (stage2/'runs'/job_id/'result.json').exists():
            subprocess.run([sys.executable,str(runner.ROOT/'scripts/run_ring_ablations.py'),
                            '--worker',job_id,'--output',str(stage2)],check=True)
    curve=json.loads((stage2/'runs'/job_id/'curve.json').read_text())
    assert [r['decisions'] for r in curve]==[2_031_616,3_014_656,5_013_504,7_503_872,10_027_008]
    short_path=root/'results/vision15-no-travel-early-2048.json'
    long_path=root/'results/vision15-no-travel-train2048-10m.json'
    short={r['decisions']:r for r in json.loads(short_path.read_text())['checkpoints']}
    long={r['decisions']:r for r in json.loads(long_path.read_text())['checkpoints']}
    for key in ['clear_rate','death_rate','timeout_rate','kills','turns']:
        assert curve[0]['sampled'][key]==short[2_031_616]['budget_clock'][key],key
    report=dict(schedule='512 physical turns through 2031616 decisions, then 2048 through 10027008',
                seed=0,evaluation_deadline=2048,travel=False,manifest=manifest,
                continuation=json.loads((stage2/'continuation.json').read_text()),
                baseline_hashes={str(p):runner.digest(p) for p in [short_path,long_path]},checkpoints=[])
    for row in curve:
        n=row['decisions'];snapshot=stage2/'runs'/job_id/'snapshots'/f'{n:012d}.pt'
        report['checkpoints'].append(dict(decisions=n,train_seconds=row['train_seconds'],
                sampled=row['sampled'],greedy=row['greedy'],checkpoint_sha256=runner.digest(snapshot),
                fixed512=short[n]['budget_clock'],fixed2048=long[n]['sampled']))
        print(json.dumps(dict(decisions=n,curriculum_clear=row['sampled']['clear_rate'],
                             fixed512_clear=short[n]['budget_clock']['clear_rate'],
                             fixed2048_clear=long[n]['sampled']['clear_rate'])),flush=True)
    args.results.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
