"""Replay compact action logs to verify masks, rewards, boundaries and outcomes."""
import argparse
from collections import Counter
import json
from pathlib import Path

from action_env import ACTIONS, legal_mask
from goal_controllers import Recovery
from bench import sha

def audit(path):
    path=Path(path);result=json.loads(path.read_text());worker=path.parent
    if sha(worker/'events.jsonl')!=result['events_sha256'] or sha(worker/'actions.jsonl')!=result['actions_sha256']:
        raise ValueError('Evidence checksum mismatch')
    events=[json.loads(x) for x in (worker/'events.jsonl').read_text().splitlines()]
    actions=[json.loads(x) for x in (worker/'actions.jsonl').read_text().splitlines()]
    if len(events)!=len(actions)+1 or len(actions)!=result['steps']:
        raise ValueError('Missing / duplicated transition')
    before=events[0]['initial_observation'];recovery=Recovery();blocked=set();noops=0;total=0.
    endpoint=None
    for i,(event,row) in enumerate(zip(events[1:],actions)):
        a=ACTIONS.index(row['action']);mask=legal_mask(before)
        for n in blocked:mask[n]=False
        if mask.tolist()!=row['mask'] or not mask[a] or event['action']!=row['action']:
            raise ValueError('Mask/action mismatch')
        after=event['next_observation'];dead=after.get('terminal')=='death'
        delta=after.get('turn',before['turn'])-before['turn']
        if not dead and (after['seq']!=before['seq']+1 or delta not in (0,1)):
            raise ValueError('Invalid action boundary')
        if event['before_seq']!=before['seq'] or row['before_seq']!=before['seq']:
            raise ValueError('Sequence mismatch')
        noop=not dead and delta==0
        noops=noops+1 if noop else 0
        if noop:blocked.add(a)
        else:blocked.clear()
        recovered=recovery.observe(before,after) if not dead else False
        reward=-.01+.2*(.995*(0 if dead or recovered else after['hp']/after['max_hp'])-before['hp']/before['max_hp'])
        if noop:reward-=.05
        if dead:reward-=10
        if recovered:reward+=10
        if abs(reward-row['reward'])>1e-8 or row['no_op']!=noop or row['turn_delta']!=delta:
            raise ValueError('Reward/no-op mismatch')
        endpoint='death' if dead else 'recovered_quiet' if recovered else None
        if endpoint and i!=len(actions)-1:raise ValueError('Actions after terminal')
        if bool(row['terminated'])!=bool(endpoint):raise ValueError('Termination mismatch')
        total+=reward;before=after
    if result['outcome'] in ('death','recovered_quiet') and endpoint!=result['outcome']:
        raise ValueError('Unverified endpoint')
    if result['outcome']=='budget_truncated' and len(actions)!=result['max_steps']:
        raise ValueError('Wrong budget boundary')
    if result['outcome']=='no_turn_stall' and noops<8:raise ValueError('Wrong stall boundary')
    if result['outcome']=='death' and sha(Path(before['evidence']))!=before['evidence_sha256']:
        raise ValueError('Death evidence mismatch')
    if abs(total-result['reward'])>1e-7:raise ValueError('Return mismatch')
    return result['outcome']

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);args=parser.parse_args()
    results=Counter()
    for path in args.root.rglob('episode.json'):results[audit(path)]+=1
    print(json.dumps(dict(results)),flush=True)
