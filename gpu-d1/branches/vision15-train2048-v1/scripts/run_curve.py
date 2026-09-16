"""Train and validate at 2048 turns; compare with the 512-turn-trained curve."""
import argparse
import json
import pathlib
import subprocess
import sys

from run_ring_ablations import ROOT,digest


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--suite',type=pathlib.Path,required=True)
    ap.add_argument('--results',type=pathlib.Path,required=True)
    args=ap.parse_args()
    subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('run_ring_ablations.py')),
                    '--output',str(args.suite),'--steps','10000000','--seeds','0',
                    '--variants','vision15_no_travel'],check=True)
    manifest=json.loads((args.suite/'manifest.json').read_text())
    job=manifest['jobs'][0]
    baseline=ROOT.parents[1]/'learning-runs/vision15-no-travel-early-10m'
    old_manifest=json.loads((baseline/'manifest.json').read_text())
    old_job=old_manifest['jobs'][0]
    assert {k:v for k,v in job.items() if k!='turn_limit'}=={k:v for k,v in old_job.items() if k!='turn_limit'}
    assert job['turn_limit']==2048 and old_job['turn_limit']==512
    assert manifest['maps']==old_manifest['maps']
    old_result=ROOT.parents[1]/'results/vision15-no-travel-early-2048.json'
    old={r['decisions']:r for r in json.loads(old_result.read_text())['checkpoints']}
    folder=args.suite/'runs'/job['id']
    curve=json.loads((folder/'curve.json').read_text())
    assert len(curve)==9 and curve[-1]['decisions']==10_027_008
    report=dict(training_deadline=2048,evaluation_deadline=2048,clock='physical turns / 2048',
                seed=0,baseline_sha256=digest(old_result),manifest=manifest,
                summarizer_sha256=digest(pathlib.Path(__file__)),checkpoints=[])
    for row in curve:
        decisions=row['decisions']
        snapshot=folder/'snapshots'/f'{decisions:012d}.pt'
        assert snapshot.exists()
        report['checkpoints'].append(dict(decisions=decisions,train_seconds=row['train_seconds'],
                checkpoint_sha256=digest(snapshot),sampled=row['sampled'],greedy=row['greedy'],
                trained512_validated2048=old[decisions]['budget_clock'],
                trained512_train_seconds=old[decisions]['train_seconds']))
        print(json.dumps(dict(decisions=decisions,train_seconds=row['train_seconds'],
              clear_rate=row['sampled']['clear_rate'],death_rate=row['sampled']['death_rate'],
              timeout_rate=row['sampled']['timeout_rate'],
              trained512_clear_rate=old[decisions]['budget_clock']['clear_rate'])),flush=True)
    args.results.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
