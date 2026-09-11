"""Carry champion and persistent learner into a clean protocol lineage.

No simulations are launched. Old replay, pending cycles, evaluation caches and
optimizer tensors with obsolete input shapes remain in the original run.
"""
import argparse
import json
import time
from pathlib import Path
from model import load_model, save_model
from general_env import sha, ENGINE, HERE
from features import FEATURE_VERSION
from train_crawl_agent import write


def prepare_successor(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if target.exists():
        raise FileExistsError(target)
    status = json.loads((source/'latest_status.json').read_text())
    completed = status['completed_cycles']
    ready = source/'learner'/f'cycle-{completed-1:04d}.ready.json'
    record = json.loads(ready.read_text())
    learner = Path(record['path'])
    if sha(learner) != record['sha256']:
        raise ValueError('source committed learner checksum mismatch')
    champion = max((source/'champions').glob('V*.pt'),key=lambda p:int(p.stem[1:]))
    lineage = {'source':str(source),'completed_cycles':completed,'models':{},
               'replay_migration':'none: start current-protocol experience',
               'optimizer_migration':'reset incompatible feature dimensions; preserve weights'}
    for role, old, new in [('champion',champion,target/'champions'/'V0.pt'),
                           ('learner',learner,target/'learner'/'initial.pt')]:
        model,payload = load_model(old)
        save_model(new,model,{**payload.get('metadata',{}),'source_checkpoint':str(old),
                             'source_sha256':sha(old)})
        lineage['models'][role]={'source':str(old),'source_sha256':sha(old),
                                'path':str(new),'sha256':sha(new)}
    config = json.loads((source/'config.json').read_text())
    config.update(learner_version='score-policy-v2',feature_version=FEATURE_VERSION,
                  started_unix=time.time())
    # Carry the previous weakest-seed curriculum through the protocol change,
    # without treating any old transitions as current-policy training examples.
    for path in (source/'replay').glob(f'cycle-{completed-1:04d}-*.result.json'):
        data = json.loads(path.read_text())
        suffix = path.name.removeprefix(f'cycle-{completed-1:04d}-')
        if suffix.split('.')[0].isdigit():
            write(target/'replay'/f'bootstrap-{suffix}', {**data,'source_result':str(path)})
    write(target/'config.json',config)
    write(target/'lineage.json',lineage)
    write(target/'environment_version.txt',{'engine_sha256':sha(ENGINE),
          'bridge_sha256':sha(HERE/'general_bridge.lua'),'feature_version':FEATURE_VERSION})
    write(target/'latest_status.json',{'phase':'prepared_not_running','completed_cycles':0,
          'source_run':str(source),'champion':str(target/'champions'/'V0.pt'),
          'learner':str(target/'learner'/'initial.pt')})
    return lineage


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path); parser.add_argument('target',type=Path)
    args=parser.parse_args()
    print(json.dumps(prepare_successor(args.source,args.target),indent=2))
