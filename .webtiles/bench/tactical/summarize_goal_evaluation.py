"""Policy-separated frozen-evaluation results and paired selection failures."""
import argparse
from collections import Counter,defaultdict,deque
import json
from pathlib import Path
from bench import sha
from train_encounters import write

def summarize(rows):
    grouped=defaultdict(dict)
    for r in rows:
        key=(r['case_id'],r['policy'])
        if r['policy'] in grouped[r['case_id']]: raise ValueError('Duplicate case/policy: '+str(key))
        grouped[r['case_id']][r['policy']]=r
    policies=sorted({r['policy'] for r in rows})
    cohorts=sorted({r['cohort'] for r in rows})
    report=dict(by_cohort={},by_seed={},failures=[],repeat_mismatches=[],selector_decisions=0)
    for cohort in cohorts:
        report['by_cohort'][cohort]={p:dict(Counter(r['outcome'] for r in rows
            if r['cohort']==cohort and r['policy']==p)) for p in policies}
    for seed in sorted({r['seed'] for r in rows}):
        report['by_seed'][seed]=dict(Counter(r['outcome'] for r in rows
            if r['seed']==seed and r['policy']=='selector'))
    for case,ps in grouped.items():
        if 'selector' not in ps:continue
        r=ps['selector'];report['selector_decisions']+=r['decisions']
        corresponding=ps.get(r['option'])
        if corresponding and corresponding['outcome']!=r['outcome']:
            report['repeat_mismatches'].append(dict(case_id=case,selected=r['option'],
                selector_outcome=r['outcome'],fixed_outcome=corresponding['outcome']))
        if r['outcome']=='recovered_quiet': continue
        good=[p for p,v in ps.items() if p!='selector' and v['outcome']=='recovered_quiet']
        complete=len(ps)==7 and all(v['outcome']!='harness_error' for v in ps.values())
        kind=('incomplete_or_error' if r['outcome']=='harness_error' else
              'selection_miss' if good else 'controller_coverage_gap' if complete else 'incomplete_or_error')
        report['failures'].append(dict(case_id=case,seed=r['seed'],cohort=r['cohort'],
            option=r['option'],outcome=r['outcome'],kind=kind,successful_alternatives=good,
            worker=r['worker'],events=r.get('events',[]),actions=r.get('actions',{})))
    report['failure_types']=dict(Counter(f['kind'] for f in report['failures']))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();rows=json.loads((a.root/'results.json').read_text());r=summarize(rows)
    for f in r['failures']:
        trace=Path(f['worker'])/'transitions.jsonl';recent=deque(maxlen=12)
        if trace.exists():
            with trace.open() as stream:
                for line in stream:
                    t=json.loads(line);s=t['observation'];n=t['next_observation']
                    recent.append(dict(turn=s['turn'],floor=s['floor'],hp=s['hp'],max_hp=s['max_hp'],
                        action=t['action'],after_hp=n.get('hp'),status=s.get('status'),
                        safe=s.get('safe'),unseen=s.get('unseen'),monsters=s['monsters'],
                        messages=n.get('messages',{})))
            f['last_decisions']=list(recent);f['trace_sha256']=sha(trace)
    r['results_sha256']=sha(a.root/'results.json');r['manifest_sha256']=sha(a.root/'manifest.json')
    write(a.output,r);print(json.dumps({k:v for k,v in r.items() if k!='failures'},indent=2))
