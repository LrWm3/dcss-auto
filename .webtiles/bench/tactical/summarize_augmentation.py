"""Report synthetic controller robustness without fitting or mixing families."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
from bench import HERE,sha
from train_encounters import write

def summarize(rows,variants,parents):
    grouped=defaultdict(dict)
    for r in rows:
        if r['policy'] in grouped[r['case_id']]: raise ValueError('Duplicate case/policy')
        grouped[r['case_id']][r['policy']]=r
    policies=sorted({r['policy'] for r in rows})
    report=dict(by_policy={},by_family={},by_hp={},winning_sets={},
        no_recovery=[],mixed_outcomes=[],parent_flips=[],incomplete=[],
        decisions=sum(r['decisions'] for r in rows),trials=len(rows))
    def counts(rs):return {p:dict(Counter(r['outcome'] for r in rs if r['policy']==p)) for p in policies}
    report['by_policy']=counts(rows)
    for f in sorted({r['family_id'] for r in rows}):
        report['by_family'][f]=counts([r for r in rows if r['family_id']==f])
    for hp in sorted({r['recipe']['hp_percent'] for r in rows}):
        report['by_hp'][hp]=counts([r for r in rows if r['recipe']['hp_percent']==hp])
    for v in variants:
        ps=grouped[v['id']]
        if len(ps)!=6 or any(r['outcome']=='harness_error' for r in ps.values()):
            report['incomplete'].append(v['id']);continue
        wins=sorted(p for p,r in ps.items() if r['outcome']=='recovered_quiet')
        report['winning_sets'][v['id']]=wins
        if not wins:report['no_recovery'].append(v['id'])
        if wins and any(r['outcome']=='death' for r in ps.values()):report['mixed_outcomes'].append(v['id'])
        for policy,r in ps.items():
            parent=parents[v['family_id']].get(policy)
            if parent in ('death','recovered_quiet') and r['outcome'] in ('death','recovered_quiet') and parent!=r['outcome']:
                report['parent_flips'].append(dict(case_id=v['id'],policy=policy,
                    recipe=v['recipe'],parent=parent,variant=r['outcome']))
    report['outcomes']=dict(Counter(r['outcome'] for r in rows))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    m=json.loads((a.root/'manifest.json').read_text());rows=json.loads((a.root/'results.json').read_text())
    variants=json.loads((a.root/'variants.json').read_text());parents={}
    for f in m['families']:
        rs=json.loads((HERE/f['benchmark']/'results.json').read_text())
        parents[f['id']]={r['policy']:r['outcome'] for r in rs if r['case_id']==f['case_id'] and r['policy']!='selector'}
    report=summarize(rows,variants,parents)
    report.update(results_sha256=sha(a.root/'results.json'),variants_sha256=sha(a.root/'variants.json'),
        manifest_sha256=sha(a.root/'manifest.json'),parent_outcomes=parents)
    write(a.root/'analysis.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('winning_sets','parent_flips')},indent=2))
