"""Validate five frozen policies with original action choices and 2048 turns."""
import argparse
import json
import pathlib
import time

import torch

from evaluate_deadline_transfer import evaluate
from evaluate_policy_transfer import Policy
from learn_env_ring_multi import Env
from run_ring_ablations import ROOT, corpus_manifest, digest


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=pathlib.Path, required=True)
    args = ap.parse_args()
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    runs = ROOT.parents[1]/'learning-runs'
    original = runs/'vision15-frontier-30m'
    manifest = json.loads((original/'manifest.json').read_text())
    corpus = pathlib.Path(manifest['corpus'])
    assert corpus_manifest(corpus) == manifest['maps']
    libraries = {}
    for actions, job_id in [(9,'vision15_no_travel-seed0'), (10,'vision15_travel-seed0')]:
        config = json.loads((original/'runs'/job_id/'config.json').read_text())
        matches = [p for p in (original/'build').glob('*.so') if digest(p)==config['library_sha256']]
        assert len(matches)==1
        libraries[actions] = matches[0]
        assert digest(matches[0]) == matches[0].with_suffix('.sha256').read_text().strip()
    cases = [('optional_travel_30m','vision15-frontier-30m','vision15_travel-seed0'),
             ('no_travel_30m','vision15-frontier-30m','vision15_no_travel-seed0'),
             ('no_travel_time_matched','vision15-no-travel-time-match','vision15_no_travel-seed0'),
             ('forced_turn_trained','vision15-forced-travel-30m','forced_turn512-seed0'),
             ('forced_decision_trained','vision15-forced-travel-30m','forced_decision512-seed0')]
    report = dict(training_performed=False, forced_travel=False, physical_turn_limit=2048,
                  validation_maps=32, episodes_per_map=32,
                  sources={p:digest(pathlib.Path(__file__).with_name(p)) for p in
                           ['evaluate_unforced_2048.py','evaluate_deadline_transfer.py','evaluate_policy_transfer.py']},
                  libraries={str(k):digest(v) for k,v in libraries.items()}, policies={})
    start = time.perf_counter()
    for label,suite_name,job_id in cases:
        source = runs/suite_name/'runs'/job_id/'latest.pt'
        before = digest(source)
        saved = torch.load(source,map_location='cpu',weights_only=False)
        actions = saved['model']['actor.bias'].numel()
        assert saved['model']['body.0.weight'].shape[1]==958
        assert not saved['job']['no_xy'] and not saved['job']['no_ring']
        assert saved['job']['frames']==1
        source_manifest = json.loads((runs/suite_name/'manifest.json').read_text())
        assert source_manifest['maps']==manifest['maps']
        model = Policy(saved['job']['width'],actions).cuda().eval()
        model.load_state_dict(saved['model'])
        env = Env(batch=1024,enemies=24,seed=900000,corpus=corpus/'validation',
                  map_limit=32,map_filter=-2,library_path=libraries[actions],limit=512)
        # The native ABI already accepts a runtime physical deadline. Constructor
        # validation is specific to the old training task; no native rebuild or
        # change to live training code is needed for evaluation.
        env.limit = 2048
        assert env.action_size==actions
        if actions==10:
            assert (env.mask[:,8]==1).all()  # Wait remains available even with travel.
        evaluations = {}
        trained_clock = 'decisions' if saved['job'].get('decision_limit',False) else 'physical'
        for name,clock,denominator in [('budget_clock','physical',2048),
                                       ('training_clock',trained_clock,512)]:
            results = {mode:evaluate(model,env,mode,False,max_decisions=2048,
                                     clock_mode=clock,clock_denominator=denominator,physical_limit=2048)
                       for mode in ['sampled','greedy']}
            evaluations[name] = dict(clock_mode=clock,clock_denominator=denominator,**results)
            print(label,name,json.dumps({k:results['sampled'][k] for k in
                  ['clear_rate','death_rate','timeout_rate','kills','turns','policy_decisions','travel_uses']}),flush=True)
        assert digest(source)==before
        report['policies'][label] = dict(checkpoint_sha256=before,decisions=saved['decisions'],
                                        train_seconds=saved['train_seconds'],actions=actions,evaluations=evaluations)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
        del env
    report['evaluation_seconds'] = time.perf_counter()-start
    args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
