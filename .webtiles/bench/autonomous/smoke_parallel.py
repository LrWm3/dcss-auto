"""Compare six identical checkpoint continuations serially and in parallel."""
import argparse
import json
from pathlib import Path
import time
import torch
from counterfactual import evaluate_checkpoint


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('case', type=Path)
    parser.add_argument('model', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    records, timings = [], []
    for workers in (1, 6):
        started = time.perf_counter()
        result = evaluate_checkpoint(args.case, args.output/str(workers), args.model,
                                     top_k=2, random_k=1, continuations=2,
                                     continuation_steps=20, max_workers=workers)
        timings.append(time.perf_counter()-started)
        records.append(result)
    errors = [o for result in records for r in result for o in r['outcomes'] if 'error' in o]
    summary = {'serial_seconds':timings[0], 'parallel_seconds':timings[1],
               'matched':records[0]==records[1], 'errors':errors, 'records':records}
    (args.output/'results.json').write_text(json.dumps(summary))
    print(json.dumps({k:v for k,v in summary.items() if k!='records'}))
    if errors or not summary['matched']:
        raise SystemExit('Counterfactual equivalence failed')


if __name__ == '__main__':
    main()
