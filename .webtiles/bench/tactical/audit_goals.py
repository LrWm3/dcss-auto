"""Audit fresh goal results and success boundaries without running a game."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
from bench import HERE,sha
from goal_controllers import Recovery,clean
from train_encounters import write

def audit(root):
    manifest=json.loads((root/'manifest.json').read_text())
    for n,digest in manifest['sources'].items():
        if sha(HERE/n)!=digest: raise ValueError('Source mismatch: '+n)
    results=json.loads((root/'results.json').read_text())
    report=dict(artifacts=str(root.resolve()),manifest_sha256=sha(root/'manifest.json'),
        results_sha256=sha(root/'results.json'),phases={},by_seed={},success_boundaries=[],
        production_export=False)
    if (root/'model.json').exists(): report['model_sha256']=sha(root/'model.json')
    grouped=defaultdict(list)
    for r in results:
        grouped[r['phase']].append(r)
        if r['outcome']!='recovered_quiet': continue
        path=Path(r['worker'])/'transitions.jsonl'
        recovery=Recovery();last=None
        with path.open() as f:
            for line in f:
                t=json.loads(line);recovery.observe(t['observation'],t['next_observation']);last=t
        valid=bool(last and clean(last['next_observation']) and recovery.quiet>=20)
        if not valid: raise ValueError('Invalid success boundary: '+str(path))
        report['success_boundaries'].append(dict(case_id=r['case_id'],phase=r['phase'],
            option=r['option'],quiet_turns=recovery.quiet,trace_sha256=sha(path)))
    for phase,rows in grouped.items():
        report['phases'][phase]=dict(outcomes=dict(Counter(r['outcome'] for r in rows)),
            by_option={o:dict(Counter(r['outcome'] for r in rows if r['option']==o))
                for o in sorted({r['option'] for r in rows})})
        report['by_seed'][phase]={seed:dict(Counter(r['outcome'] for r in rows if r['seed']==seed))
            for seed in sorted({r['seed'] for r in rows})}
    if (root/'selector-repeat-checks.json').exists():
        checks=json.loads((root/'selector-repeat-checks.json').read_text())
        report['selector_repeat_agreement']=dict(total=len(checks),matching=sum(c['same_outcome'] for c in checks))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path)
    a=p.parse_args();r=audit(a.root)
    if a.output: write(a.output,r)
    print(json.dumps({k:v for k,v in r.items() if k!='success_boundaries'},indent=2))
