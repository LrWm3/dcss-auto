"""Validate compact early checkpoints without travel at 2048 physical turns."""
import argparse
import importlib.util
import json
import pathlib
import time

import torch
from torch import nn
from torch.distributions import Categorical

from learn_env_ring_multi import Env
from run_ring_ablations import ROOT, corpus_manifest, digest, library_key

HELPER = ROOT.parent/'vision15-forced-travel-v1/scripts/evaluate_deadline_transfer.py'
spec = importlib.util.spec_from_file_location('deadline_evaluator', HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class Policy(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(958,width),nn.Tanh(),nn.Linear(width,width),nn.Tanh())
        self.actor,self.critic = nn.Linear(width,9),nn.Linear(width,1)

    def forward(self, obs, mask):
        return Categorical(logits=self.actor(self.body(obs)).masked_fill(mask==0,-1e9))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--suite',type=pathlib.Path,required=True)
    ap.add_argument('--output',type=pathlib.Path,required=True)
    args = ap.parse_args()
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    manifest = json.loads((args.suite/'manifest.json').read_text())
    assert len(manifest['jobs'])==1
    job = manifest['jobs'][0]
    assert job['steps']==10_000_000 and job['turn_limit']==512 and not job['frontier_travel']
    corpus = pathlib.Path(manifest['corpus'])
    assert corpus_manifest(corpus)==manifest['maps']
    lib = args.suite/'build'/(library_key(job)+'.so')
    assert digest(lib)==lib.with_suffix('.sha256').read_text().strip()
    folder = args.suite/'runs'/job['id']
    history = {r['decisions']:r for r in json.loads((folder/'curve.json').read_text())}
    original = ROOT.parents[1]/'learning-runs/vision15-frontier-30m/runs/vision15_no_travel-seed0/curve.json'
    old = {r['decisions']:r for r in json.loads(original.read_text())}
    paths = sorted((folder/'snapshots').glob('*.pt'))
    assert len(paths)==9 and int(paths[0].stem)==0 and int(paths[-1].stem)==10_027_008
    report = dict(training_deadline=512,evaluation_deadline=2048,travel=False,
                  seed=job['seed'],validation_maps=32,episodes_per_map=32,
                  sources={str(p):digest(p) for p in [pathlib.Path(__file__),HELPER]},
                  library_sha256=digest(lib),checkpoints=[])
    start = time.perf_counter()
    for p in paths:
        before = digest(p)
        saved = torch.load(p,map_location='cpu',weights_only=False)
        assert saved['job']==job
        decisions = saved['decisions']
        row = dict(decisions=decisions,train_seconds=saved['train_seconds'],checkpoint_sha256=before,
                   original_512=history[decisions]['sampled'],reproduces_prior_run=None)
        if decisions in old:
            # Extra validation preserves PPO RNG via fork_rng; verify that the
            # replay actually matches the earlier run at shared milestones.
            row['reproduces_prior_run'] = all(history[decisions][mode][key]==old[decisions][mode][key]
                for mode in ['sampled','greedy'] for key in ['clear_rate','death_rate','timeout_rate','kills'])
        model = Policy(job['width']).cuda().eval()
        model.load_state_dict(saved['model'])
        env = Env(batch=1024,enemies=24,seed=900000,corpus=corpus/'validation',
                  map_limit=32,map_filter=-2,library_path=lib,limit=512)
        env.limit=2048
        assert env.action_size==9
        for name,denominator in [('budget_clock',2048),('training_clock',512)]:
            row[name] = helper.evaluate(model,env,'sampled',False,max_decisions=2048,
                                       clock_mode='physical',clock_denominator=denominator,physical_limit=2048)
        assert digest(p)==before
        report['checkpoints'].append(row)
        print(json.dumps(dict(decisions=decisions,train_seconds=row['train_seconds'],
              original_clear=row['original_512']['clear_rate'],clear_2048=row['budget_clock']['clear_rate'],
              clear_2048_training_clock=row['training_clock']['clear_rate'],
              reproduces_prior_run=row['reproduces_prior_run'])),flush=True)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        del env
    report['evaluation_seconds']=time.perf_counter()-start
    args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
