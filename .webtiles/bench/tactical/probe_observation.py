"""Compare a gameplay RNG sentinel with/without extra map reads on equal resets."""
import argparse
import json
from pathlib import Path
from bench import Environment

p=argparse.ArgumentParser()
p.add_argument('--case',type=Path,required=True)
p.add_argument('--teacher',type=Path,required=True)
p.add_argument('--steps',type=int,default=13)
p.add_argument('--output',type=Path,required=True)
args=p.parse_args()
args.output.mkdir(parents=True,exist_ok=False)
actions=[json.loads(x)['action'] for x in args.teacher.read_text().splitlines()]
results=[]
for reads in (0,1,10):
    env=Environment(args.output)
    try:
        state=env.reset(args.case)
        for action in actions[:args.steps]:state=env.step(action)
        env.console('for i=1,'+str(reads)+' do view.get_map() end; '
                    'crawl.take_note("RNG sentinel "..crawl.random2(1000000000)); crawl.dump_char()')
        dump=(env.work/'morgue/TacticalEustachio.txt').read_text()
        result=dict(reads=reads,turn=state['turn'],worker=str(env.work),
                    sentinel=[x.strip() for x in dump.splitlines() if 'RNG sentinel ' in x])
        results.append(result)
        print(json.dumps(result),flush=True)
    finally:env.close()
(args.output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
