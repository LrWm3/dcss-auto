"""Verify learner execution and teacher labels against recorded training states."""
import argparse
from collections import Counter, deque
import json
from pathlib import Path
import numpy as np

from action_env import ACTIONS, HISTORY, FRAME_SIZE, frame, fixed_action
from audit_action_episodes import audit
from goal_controllers import Recovery
from train_action_dagger import load_labels, stratum


def verify(result):
    worker = Path(result['worker'])
    audit(worker/'episode.json')
    data = load_labels(result)
    events = [json.loads(x) for x in (worker/'events.jsonl').read_text().splitlines()]
    actions = [json.loads(x) for x in (worker/'actions.jsonl').read_text().splitlines()]
    if len(actions)!=len(data['actions']): raise ValueError('Missing labels')
    state = events[0]['initial_observation']; recovery = Recovery()
    history = deque([np.zeros(FRAME_SIZE,dtype=np.float32) for _ in range(HISTORY-1)],maxlen=HISTORY)
    history.append(frame(state)); disagreements = 0
    for i,(event,row) in enumerate(zip(events[1:],actions)):
        mask = np.asarray(row['mask'],dtype=bool)
        teacher = fixed_action(state,mask,'pursue')
        executed = ACTIONS.index(row['action'])
        np.testing.assert_array_equal(data['observations'][i],np.concatenate(history))
        np.testing.assert_array_equal(data['masks'][i],mask)
        if (teacher!=data['actions'][i] or executed!=data['executed'][i]
                or stratum(state,teacher)!=data['groups'][i]):
            raise ValueError('Teacher/executed action or group mismatch')
        disagreements += teacher!=executed
        after = event['next_observation']
        if not after.get('terminal'):
            recovery.observe(state,after)
            history.append(frame(after,executed,after['hp']/after['max_hp']-state['hp']/state['max_hp'],recovery.quiet))
        state = after
    if disagreements!=result['disagreements']: raise ValueError('Wrong disagreement count')
    return len(actions),disagreements


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path); args=parser.parse_args()
    counts = Counter()
    for path in sorted(args.root.glob('round-[123].json')):
        for result in json.loads(path.read_text()):
            labels,disagreements = verify(result)
            counts.update(episodes=1,labels=labels,disagreements=disagreements)
    print(json.dumps(dict(counts)))
