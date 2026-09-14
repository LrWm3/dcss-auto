"""Read-only model audit plus optional paired input ablations in private games.

Held-out observations are diagnostic only, never written into training replay.
"""
import os
os.environ['DCSS_REPRESENTATION']='spatial-v6'
import argparse
import concurrent.futures
import copy
import gzip
import json
import random
from collections import Counter
from pathlib import Path
import torch
from general_env import GeneralEnvironment
from learner import policy_diagnostics
from model import load_model, tensor_for_actions
from teacher import choose_action


def input_variant(state, variant):
    state=copy.deepcopy(state)
    if variant=='no_history': state['history']=[]
    if variant=='last_move':
        for h in state.get('history',[]):
            h['action']={'kind':'MOVE','dx':1,'dy':0}
            h['hp_delta']=0
    if variant=='hp_half': state['player']['hp']/=2
    if variant=='turn_zero': state['turn']=0
    return state


def selection(model,state,variant):
    modified=input_variant(state,variant)
    with torch.no_grad():
        scores=model(tensor_for_actions(modified,modified['actions']))
        probs=scores.softmax(-1)
    i=int(scores.argmax())
    return i, {'action':modified['actions'][i], 'probability':float(probs[i]),
               'logit_range':[float(scores.min()),float(scores.max())]}


def branch(model,checkpoint,folder,variant,steps):
    counts=Counter()
    with GeneralEnvironment(folder,data_role='diagnostic') as env:
        env.record_events=False
        state=env.launch(checkpoint)
        initial={'score':state.get('score'),'turn':state.get('turn'),'level':state.get('level')}
        for _ in range(steps):
            if state.get('terminal'):break
            i,_=selection(model,state,variant)
            counts[state['actions'][i]['kind']]+=1
            state=env.step(i)
        return {'variant':variant,'checkpoint':str(checkpoint),'initial':initial,
                'final':{k:state.get(k) for k in ('score','turn','level','terminal')},
                'decisions':sum(counts.values()),'action_counts':dict(counts)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--run-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--live-steps',type=int,default=256)
    args=p.parse_args(); root=args.run_dir.resolve()
    args.output.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(1)
    model,payload=load_model(root/'champions/V0.pt')
    report={'bootstrap_metadata':payload['metadata'],'cutoff_ablation':[],
            'corrected_policy_diagnostics':{},'live_ablation':[]}
    cases=[]
    for f in sorted((root/'evaluations/screens').glob('*.json')):
        for r in json.loads(f.read_text())['evaluation']['champion']['results']:
            if not r.get('resume_checkpoint'):continue
            cp=Path(r['resume_checkpoint'])
            state=json.loads((cp/'case.json').read_text())['observation']
            variants={v:selection(model,state,v)[1] for v in
                      ('original','no_history','last_move','hp_half','turn_zero')}
            teacher=state['actions'][choose_action(state)]
            report['cutoff_ablation'].append({'seed':r['seed'],'checkpoint':str(cp),
                'hp':state['player']['hp'],'max_hp':state['player']['max_hp'],
                'monsters':len(state.get('monsters',[])), 'teacher':teacher,
                'action_counts':r.get('action_counts'),'variants':variants})
            cases.append(cp)
    # Sample retained training replay for recomputing diagnostics. Preserve
    # historical manifests, which describe the original computation.
    rng=random.Random(20260912); sample=[]; seen=0
    for f in sorted((root/'replay').glob('cycle-0002-*.jsonl.gz')):
        if 'counterfactual' in f.name:continue
        with gzip.open(f,'rt') as stream:
            for line in stream:
                row=json.loads(line)
                if not row.get('observation',{}).get('actions'):continue
                seen+=1
                if len(sample)<128:sample.append(row)
                else:
                    i=rng.randrange(seen)
                    if i<128:sample[i]=row
    for f in sorted((root/'candidates').glob('*.pt')):
        report['corrected_policy_diagnostics'][f.name]=policy_diagnostics(root/'champions/V0.pt',f,sample)
    if args.live_steps:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            jobs=[pool.submit(branch,model,cp,args.output/f'case-{i}-{v}',v,args.live_steps)
                  for i,cp in enumerate(cases[:2]) for v in ('original','no_history')]
            report['live_ablation']=[job.result() for job in jobs]
    target=args.output/'report.json'
    target.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'report':str(target),'cases':len(cases),
                     'diagnostics':report['corrected_policy_diagnostics'],
                     'live':report['live_ablation']},indent=2,allow_nan=False))


if __name__=='__main__':main()
