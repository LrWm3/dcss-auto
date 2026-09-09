"""One fixed V2 fit, training-matrix evaluation and live replay smoke checks.

This is outcome-supervised strategy selection, not per-turn RL. No deployment.
"""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from augmentation_dataset import read, verify_result
from bench import HERE, ENGINE, sha
from character_audit import load
from rich_goals import fit, select, run
from train_encounters import write


def live(task):
    entry, case, root, model = task
    return verify_result(run(entry, Path(case), Path(root), 'selector', 600, model))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    dataset = args.dataset.resolve(); root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    write(root/'status.json', dict(status='auditing'))
    audit = read(dataset/'training-index.json')
    for name, digest in audit['files'].items():
        if sha(dataset/name) != digest: raise ValueError('Dataset changed: '+name)
    training = sorted(load(dataset), key=lambda r: (r['case_id'], r['option']))
    if sha(ENGINE) != read(dataset/'manifest.json')['engine_sha256']:
        raise ValueError('Use the collection engine for live checks')
    pinned = {str(p): sha(p) for p in
              [HERE/'rich_features.py', HERE/'rich_goal_bridge.lua', HERE/'rich_goals.py',
               HERE/'run_goals.py', HERE/'goal_controllers.py',
               HERE/'models/goal-selector-v1.json', HERE/'models/goal-selector-augmented-v1.json',
               HERE.parents[1]/'rcs/codex-autocrawl.rc']}
    manifest = dict(dataset=str(dataset), dataset_index_sha256=sha(dataset/'training-index.json'),
        training_rows=len(training), training_cases=len({r['case_id'] for r in training}),
        training_seeds=sorted({r['seed'] for r in training}), epochs=1500, random_seed=42,
        script_sha256=sha(Path(__file__)), pinned=pinned, production_export=False,
        policy='All complete audited V2 training rows; one fixed fit; no tuning',
        evaluation='Training matrix only; no new held-out V2 collection available')
    write(root/'manifest.json', manifest)
    write(root/'status.json', dict(status='fitting', **manifest))
    model = fit(training, epochs=1500)
    write(root/'model.json', model)
    model = read(root/'model.json'); frozen = sha(root/'model.json')
    ids = {r['case_id'] for r in training}
    variants = {v['id']: v for f in read(dataset/'coverage.json') for v in f['variants']}
    matrix = defaultdict(dict)
    for r in read(dataset/'results.json'):
        matrix[r['case_id']][r['option']] = r
    selections = []
    for ident in sorted(ids):
        v = variants[ident]; option = select(model, v['initial']); rs = matrix[ident]
        picks = dict(candidate=option, pursue_no_berserk='pursue:0', pursue_berserk='pursue:1')
        selections.append(dict(case_id=ident, seed=rs[option]['seed'], axis=v['recipe']['axis'],
            choices={k:dict(option=o, outcome=rs[o]['outcome']) for k,o in picks.items()}))
    summary = dict(training_variants=len(selections), training_rows=len(training),
        evaluation='In-sample recorded outcomes, not held-out performance',
        outcomes={k:dict(Counter(s['choices'][k]['outcome'] for s in selections))
                  for k in ('candidate','pursue_no_berserk','pursue_berserk')})
    write(root/'selections.json', selections); write(root/'summary.json', summary)
    print(summary, flush=True)
    # One deterministic case per axis, chosen without looking at its outcome.
    sample = [next(s for s in selections if s['axis']==axis)
              for axis in ('none','skill','xl','attribute','gear','resistance')]
    tasks = [(dict(id=s['case_id'], seed=s['seed']), variants[s['case_id']]['case'],
              str(root/f'live-{i:02d}'), model) for i,s in enumerate(sample)]
    write(root/'status.json', dict(status='live_checks', model_sha256=frozen))
    checks = []
    with ProcessPoolExecutor(max_workers=6) as pool:
        for s,r in zip(sample, pool.map(live,tasks)):
            expected = s['choices']['candidate']
            checks.append(dict(case_id=s['case_id'], result=r, expected=expected,
                passed=r['option']==expected['option'] and r['outcome']==expected['outcome']
                       and r.get('evidence_verified',False)))
            write(root/'live-checks.json', checks)
    for name,digest in pinned.items():
        if sha(Path(name)) != digest: raise ValueError('Pinned file changed: '+name)
    if sha(root/'model.json') != frozen: raise ValueError('Model changed')
    if not all(c['passed'] for c in checks): raise RuntimeError('Live replay mismatch; do not deploy')
    write(root/'completion.json', dict(model_sha256=frozen, live_checks=6,
        live_passed=6, production_export=False, held_out_evaluated=False, **summary))
    write(root/'status.json', dict(status='complete', model_sha256=frozen, production_export=False))


if __name__ == '__main__':
    main()
