"""Audit complete chained runs; optionally compare deterministic replays."""
import argparse
from collections import Counter
import json
from pathlib import Path

from audit_action_episodes import audit
from benchmark_chains import ChainRecovery, check_boundary
from benchmark_transport import digest


def inspect(row):
    if row['outcome']=='harness_error':
        raise ValueError('Harness error in matrix')
    worker=Path(row['worker'])
    audit(worker/'episode.json', recovery_factory=ChainRecovery)
    events=[json.loads(line) for line in (worker/'events.jsonl').read_text().splitlines()]
    states=[events[0]['initial_observation']]+[e['next_observation'] for e in events[1:]]
    previous_stage=0;boundaries=[]; blocked=0; cooldown_combat=0
    for s in states:
        if s.get('terminal'):
            continue
        c=s['chain'];b=c.get('boundary')
        if c['stage'] != previous_stage:
            if c['stage'] != previous_stage+1 or not b or b['stage'] != c['stage']:
                raise ValueError('Skipped wave or missing boundary')
            check_boundary(b)
            if b['after']['alive'] != len(row['waves'][c['stage']-1]):
                raise ValueError('Incomplete wave spawn')
            boundaries.append(b)
        elif b:
            raise ValueError('Duplicated boundary')
        previous_stage=c['stage']
        # DUR_EXHAUSTED is a legacy enum, not the current berserk cooldown.
        cooldown=c['native'].get('berserk_cooldown', 0)>0 or bool(s.get('cooldown'))
        if s.get('monsters') and cooldown:
            cooldown_combat+=1
        if cooldown or c['native']['berserk']>0:
            from action_env import legal_mask
            if legal_mask(s)[-1]:
                raise ValueError('Berserk incorrectly available')
            blocked+=1
    if boundaries != row['boundaries']:
        raise ValueError('Boundary summary does not match trace')
    if row['outcome']=='recovered_quiet':
        last=states[-1]['chain']
        if last['stage']!=last['total'] or last['native']['alive']:
            raise ValueError('Premature success')
    return dict(boundaries=len(boundaries)-1, blocked_states=blocked,
                cooldown_combat_states=cooldown_combat,
                trace=[digest(s) for s in states],
                actions=[e['action'] for e in events[1:]])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('root',type=Path)
    p.add_argument('--compare',type=Path)
    args=p.parse_args()
    rows=json.loads((args.root/'trials.json').read_text())
    results={(r['index'],r['policy']):inspect(r) for r in rows}
    if len(results)!=len(rows):
        raise ValueError('Duplicate run')
    if args.compare:
        other=json.loads((args.compare/'trials.json').read_text())
        expected={(r['index'],r['policy']):inspect(r) for r in other}
        if results != expected:
            raise ValueError('Replay divergence')
    summary=dict(runs=len(rows), outcomes=dict(Counter(r['outcome'] for r in rows)),
                 boundaries=sum(r['boundaries'] for r in results.values()),
                 blocked_states=sum(r['blocked_states'] for r in results.values()),
                 cooldown_combat_states=sum(r['cooldown_combat_states'] for r in results.values()),
                 deterministic_comparison=bool(args.compare))
    (args.root/'audit.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
