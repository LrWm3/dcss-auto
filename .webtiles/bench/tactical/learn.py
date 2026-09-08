"""Fit an encounter policy from successful demonstrations, then small online RL.

All data is from one seed family: evaluation here is in-sample only.
"""
import argparse
import collections
import copy
import json
import random
from pathlib import Path

from experiment import episode, key


def imitate(workers):
    counts=collections.defaultdict(collections.Counter)
    for worker in workers:
        result=json.loads((worker/'result.json').read_text())
        if result['outcome']!='safe_recovery':
            raise ValueError('Demonstration did not end in safe recovery')
        transitions=[json.loads(x) for x in (worker/'transitions.jsonl').read_text().splitlines()]
        decisions=[json.loads(x) for x in (worker/'rewards.jsonl').read_text().splitlines()]
        if len(transitions)!=len(decisions):raise ValueError('Unaligned demonstration')
        for row,decision in zip(transitions,decisions):
            if row['action']!=decision['action']:raise ValueError('Action mismatch')
            counts[key(row['observation'])][decision['option']]+=1
    # Positive initial preference for demonstrated actions; unseen choices zero.
    return {k:{a:10*n/sum(actions.values()) for a,n in actions.items()}
            for k,actions in counts.items()}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--case',required=True,type=Path)
    p.add_argument('--teacher',required=True,type=Path,action='append')
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--episodes',type=int,default=6)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    q=imitate(args.teacher);teacher=copy.deepcopy(q);rng=random.Random(1);results=[]
    (args.output/'imitation.json').write_text(json.dumps(q,indent=2)+'\n')
    for phase,training,fresh in ([('imitation',False,False)]*2+
                                [('rl',True,False)]*args.episodes+
                                [('refined',False,False)]*2+
                                [('imitation',False,True)]):
        model=teacher if phase=='imitation' else q
        result=episode(args.case,args.output,'q',model,rng,240,training,fresh)
        result['phase']=phase;results.append(result)
        print(json.dumps(result),flush=True)
        (args.output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
        (args.output/'refined.json').write_text(json.dumps(q,indent=2)+'\n')
        if result['outcome']=='harness_error':break


if __name__=='__main__':main()
