"""Reconstruct fresh labels and verify model execution for a completed cycle."""
import argparse
import json
from pathlib import Path
import numpy as np
import torch
import bench
from action_env import ACTIONS
from audit_action_episodes import audit
from direction_policy import DirectionPolicy
from train_direction_pilot import extract
from train_action_imitation import pool_run


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path)
    root=p.parse_args().root.resolve();manifest=json.loads((root/'manifest.json').read_text())
    parent=Path(manifest['parent']);metadata=json.loads((root/'dataset.json').read_text())
    for name in ('direction_policy.py','action_env.py','goal_controllers.py'):
        if bench.sha(bench.HERE/name)!=manifest['sources'][name]:raise ValueError('Implementation changed')
    for path,expected in [(root/'training.npz',metadata['sha256']),
                          (root/'new-labels.npz',metadata['new_labels_sha256']),
                          (parent/'training.npz',metadata['parent_sha256'])]:
        if bench.sha(path)!=expected:raise ValueError('Dataset changed')
    collection=json.loads((root/'collection.json').read_text())
    rows=[r for batch in pool_run(extract,collection) for r in batch]
    reconstructed=dict(features=np.stack([r[0] for r in rows]),masks=np.stack([r[1] for r in rows]),
        actions=np.asarray([r[2] for r in rows]),groups=np.asarray([r[3] for r in rows]),executed=np.asarray([r[4] for r in rows]))
    with np.load(root/'training.npz') as full,np.load(root/'new-labels.npz') as fresh,np.load(parent/'training.npz') as old:
        for key in reconstructed:
            np.testing.assert_array_equal(fresh[key],reconstructed[key])
            np.testing.assert_array_equal(full[key],np.concatenate([old[key],fresh[key]]))
    torch.set_num_threads(1);decisions=episodes=0
    final=json.loads((root/'train-evaluation.json').read_text())+json.loads((root/'validation-evaluation.json').read_text())
    for checkpoint,expected,results in [(parent/'capped.pt',manifest['initial_model_sha256'],collection),
            (root/'capped.pt',json.loads((root/'capped-fit.json').read_text())['model_sha256'],final)]:
        if bench.sha(checkpoint)!=expected:raise ValueError('Checkpoint changed')
        model=DirectionPolicy();model.load_state_dict(torch.load(checkpoint,weights_only=True));model.eval()
        for result in results:
            worker=Path(result['worker']);audit(worker/'episode.json')
            events=[json.loads(x) for x in (worker/'events.jsonl').read_text().splitlines()]
            actions=[json.loads(x) for x in (worker/'actions.jsonl').read_text().splitlines()]
            state=events[0]['initial_observation']
            for event,row in zip(events[1:],actions):
                if model.act(state,row['mask'])!=ACTIONS.index(row['action']):raise ValueError('Model/action mismatch')
                decisions+=1;state=event['next_observation']
            episodes+=1
    print(json.dumps(dict(new_labels=len(rows),model_episodes=episodes,model_decisions=decisions)))


if __name__=='__main__':main()
