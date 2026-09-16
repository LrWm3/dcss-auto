"""Apply forced travel to existing 15x15 policies, with no weight updates."""
import argparse
import json
import math
import pathlib
import time

import torch
from torch import nn
from torch.distributions import Categorical

from evaluate_deadline_transfer import evaluate
from learn_env_ring_multi import Env
from run_ring_ablations import ROOT, corpus_manifest, digest, library_key


class Policy(nn.Module):
    def __init__(self, width, actions):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(958, width), nn.Tanh(), nn.Linear(width, width), nn.Tanh())
        self.actor, self.critic = nn.Linear(width, actions), nn.Linear(width, 1)

    def forward(self, obs, mask):
        logits = self.actor(self.body(obs))
        if logits.shape[1] == 9 and mask.shape[1] == 10:
            # External controller adds no learned action parameters. The tenth
            # action is the only valid action when available, otherwise masked.
            forced = mask[:, 9] > 0
            assert (mask[forced, :9] == 0).all()
            logits = torch.cat((logits, torch.zeros_like(logits[:, :1])), dim=1)
        return Categorical(logits=logits.masked_fill(mask == 0, -1e9))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=pathlib.Path, required=True)
    args = ap.parse_args()
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    runs = ROOT.parents[1]/'learning-runs'
    forced_suite = runs/'vision15-forced-travel-30m'
    forced_manifest = json.loads((forced_suite/'manifest.json').read_text())
    corpus = pathlib.Path(forced_manifest['corpus'])
    assert corpus_manifest(corpus) == forced_manifest['maps']
    budget_jobs = {j['decision_limit']: j for j in forced_manifest['jobs']}
    cases = [('optional_travel_30m', 'vision15-frontier-30m', 'vision15_travel-seed0'),
             ('no_travel_30m', 'vision15-frontier-30m', 'vision15_no_travel-seed0'),
             ('no_travel_time_matched', 'vision15-no-travel-time-match', 'vision15_no_travel-seed0')]
    report = dict(training_performed=False, script_sha256=digest(pathlib.Path(__file__)),
                  evaluator_sha256=digest(pathlib.Path(__file__).with_name('evaluate_deadline_transfer.py')),
                  policies={})
    start = time.perf_counter()
    for label, suite_name, job_id in cases:
        suite = runs/suite_name
        source = suite/'runs'/job_id/'latest.pt'
        source_hash = digest(source)
        saved = torch.load(source, map_location='cpu', weights_only=False)
        job = saved['job']
        assert not job['no_xy'] and not job['no_ring'] and job['frames'] == 1
        actions = saved['model']['actor.bias'].numel()
        model = Policy(job['width'], actions).cuda().eval()
        model.load_state_dict(saved['model'])
        original = json.loads((suite/'runs'/job_id/'result.json').read_text())['final']
        source_manifest = json.loads((suite/'manifest.json').read_text())
        assert source_manifest['maps'] == forced_manifest['maps']
        config = json.loads((suite/'runs'/job_id/'config.json').read_text())
        original_libs = [p for p in (suite/'build').glob('*.so') if digest(p)==config['library_sha256']]
        assert len(original_libs)==1
        evaluations = {}
        variants = [('original', None, False), ('forced_turn512', False, False),
                    ('forced_decision512', True, False), ('forced_decision512_physical_clock', True, True)]
        for variant, decision_limit, physical_clock in variants:
            lib = original_libs[0] if decision_limit is None else forced_suite/'build'/(library_key(budget_jobs[decision_limit])+'.so')
            assert digest(lib)==lib.with_suffix('.sha256').read_text().strip()
            env = Env(batch=1024, enemies=24, seed=900000, corpus=corpus/'validation',
                      map_limit=32, map_filter=-2, library_path=lib, limit=512)
            results = {mode: evaluate(model, env, mode, physical_clock) for mode in ['sampled', 'greedy']}
            if variant=='original':
                for mode in results:
                    for key in ['clear_rate','death_rate','timeout_rate','kills','floor_coverage','turns']:
                        assert math.isclose(results[mode][key], original[mode][key], rel_tol=0, abs_tol=1e-7 if key=='floor_coverage' else 0), (label,mode,key,results[mode][key],original[mode][key])
            evaluations[variant] = dict(library_sha256=digest(lib), **results)
            print(label, variant, json.dumps({k:v for k,v in results['sampled'].items() if k!='maps'}), flush=True)
            del env
        assert digest(source)==source_hash
        report['policies'][label] = dict(checkpoint_sha256=source_hash, decisions=saved['decisions'],
                                        train_seconds=saved['train_seconds'], actions=actions, evaluations=evaluations)
        args.output.write_text(json.dumps(report, indent=2)+'\n')
    report['evaluation_seconds'] = time.perf_counter()-start
    args.output.write_text(json.dumps(report, indent=2)+'\n')


if __name__=='__main__':
    main()
