"""Measure successful-clear turn tails under the existing 512-decision rule."""
import argparse
import json
import pathlib

import torch

from evaluate_deadline_transfer import evaluate
from evaluate_policy_transfer import Policy
from learn_env_ring_multi import Env
from run_ring_ablations import ROOT, corpus_manifest, digest, library_key


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', type=pathlib.Path, required=True)
    args = ap.parse_args()
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    runs = ROOT.parents[1]/'learning-runs'
    suite = runs/'vision15-forced-travel-30m'
    manifest = json.loads((suite/'manifest.json').read_text())
    job = next(j for j in manifest['jobs'] if j['decision_limit'])
    corpus = pathlib.Path(manifest['corpus'])
    assert corpus_manifest(corpus)==manifest['maps']
    lib = suite/'build'/(library_key(job)+'.so')
    assert digest(lib)==lib.with_suffix('.sha256').read_text().strip()
    cases = [('optional_travel_30m','vision15-frontier-30m','vision15_travel-seed0'),
             ('no_travel_30m','vision15-frontier-30m','vision15_no_travel-seed0'),
             ('no_travel_time_matched','vision15-no-travel-time-match','vision15_no_travel-seed0'),
             ('forced_turn_trained','vision15-forced-travel-30m','forced_turn512-seed0'),
             ('forced_decision_trained','vision15-forced-travel-30m','forced_decision512-seed0')]
    expected = [0.8515625,0.775390625,0.806640625,0.87109375,0.8828125]
    report = dict(training_performed=False, deadline='512 outer decisions', clock='decisions/512',
                  library_sha256=digest(lib), sources={p:digest(pathlib.Path(__file__).with_name(p))
                  for p in ['evaluate_turn_distribution.py','evaluate_deadline_transfer.py','evaluate_policy_transfer.py']}, policies={})
    for (label,suite_name,job_id), clear_rate in zip(cases,expected):
        source = runs/suite_name/'runs'/job_id/'latest.pt'
        before = digest(source)
        saved = torch.load(source,map_location='cpu',weights_only=False)
        model = Policy(saved['job']['width'],saved['model']['actor.bias'].numel()).cuda().eval()
        model.load_state_dict(saved['model'])
        env = Env(batch=1024,enemies=24,seed=900000,corpus=corpus/'validation',
                  map_limit=32,map_filter=-2,library_path=lib,limit=512)
        result = evaluate(model,env,'sampled',False)
        assert result['clear_rate']==clear_rate
        assert digest(source)==before
        report['policies'][label] = dict(checkpoint_sha256=before, **result)
        print(label,json.dumps({k:result[k] for k in ['turn_distribution','clear_turn_thresholds']}),flush=True)
        del env
    args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':
    main()
