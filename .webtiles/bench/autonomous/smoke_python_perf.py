"""Small Python-overhead check with exact trained-weight comparison."""
import argparse
import inspect
import json
from pathlib import Path
import time
import torch
from model import load_model, save_model
from train_model import train_behavioral_clone, train_q_finetune, train_counterfactual_preferences
from teacher import choose_action
from evaluate import evaluate_model


def main():
    p = argparse.ArgumentParser()
    p.add_argument('output', type=Path)
    p.add_argument('--reference', type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(1)
    root = Path(__file__).parent / 'artifacts'
    model_path = root / 'foundation-general-training-v4/champions/V0.pt'
    source = json.loads((root/'transport-carryover-baseline-v1/results.json').read_text())
    rows = [{'observation':s, 'teacher_action_index':choose_action(s),
             'action_index':choose_action(s), 'return':10}
            for run in source['runs'] for s in run['observations'][:30]]
    prefs = [{'observation':rows[i]['observation'], 'action_index':j, 'return':10*j}
             for i in (0,15,30) for j in (0,1)]
    model, _ = load_model(model_path)
    start = time.perf_counter()
    model, _ = train_behavioral_clone(rows, epochs=3, seed=17, model=model)
    train_q_finetune(model, rows, epochs=3)
    train_counterfactual_preferences(model, prefs, anchors=rows)
    training_seconds = time.perf_counter()-start
    save_model(a.output/'trained.pt', model)
    weights_equal = None
    if a.reference:
        old, _ = load_model(a.reference/'trained.pt')
        weights_equal = all(torch.equal(v,old.state_dict()[k]) for k,v in model.state_dict().items())
    kwargs = {'cache_dir':a.output/'cache'} if 'cache_dir' in inspect.signature(evaluate_model).parameters else {}
    timings, scores = [], []
    for i in range(2):
        start = time.perf_counter()
        results = evaluate_model(model_path,a.output/f'eval-{i}', ['910000000000','910000000001'],
                                 steps=20, total_steps=40, **kwargs)
        timings.append(time.perf_counter()-start)
        scores.append([r.get('score') for r in results])
        if any('error' in r for r in results):
            raise RuntimeError(results)
    result = dict(training_seconds=training_seconds, evaluation_seconds=timings,
                  scores=scores, weights_equal=weights_equal)
    (a.output/'results.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
    if weights_equal is False:
        raise SystemExit('Training update changed')


if __name__ == '__main__':
    main()
