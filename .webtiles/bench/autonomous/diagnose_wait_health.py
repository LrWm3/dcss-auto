"""Diagnostic-only health interventions on observed training states."""
import os
os.environ['DCSS_REPRESENTATION']='spatial-v6'
import copy,gzip,json
from pathlib import Path
from collections import Counter
import torch
from model import load_model,tensor_for_actions
from teacher import choose_action,_actions
from bootstrap_repair import write

def main():
    torch.set_num_threads(1)
    root=Path(__file__).parent/'artifacts/v6-bootstrap-repair-02'
    model,_=load_model(root/'round-00/model.pt')
    groups={'WAIT':[],'MOVE':[]}
    for file in sorted((root/'demonstrations').glob('*.jsonl.gz')):
        per_file=Counter()
        with gzip.open(file,'rt') as stream:
            for line in stream:
                r=json.loads(line);s=r['observation'];a=_actions(s)
                kind=a[choose_action(s)]['kind']
                if kind not in groups or per_file[kind]>=24 or s.get('monsters'):continue
                if not any(x['kind']=='MOVE' for x in a):continue
                groups[kind].append(s);per_file[kind]+=1
                if all(per_file[k]>=24 for k in groups):break
    report={}
    for group,states in groups.items():
        result={}
        for hp_mode in ('original','full','half'):
            confusion=Counter();prob=[]
            for original in states:
                s=copy.deepcopy(original);p=s['player']
                if hp_mode=='full':p['hp']=p['max_hp']
                if hp_mode=='half':p['hp']=max(1,p['max_hp']//2)
                # The bridge exports HP twice; keep both representations consistent.
                s['hp']=[p['hp'],p['max_hp']]
                a=_actions(s);teacher=choose_action(s)
                with torch.no_grad():logits=model(tensor_for_actions(s,a));i=int(logits.argmax())
                confusion[a[teacher]['kind']+' -> '+a[i]['kind']]+=1
                prob.append(float(logits.softmax(-1)[next(j for j,x in enumerate(a) if x['kind']=='WAIT')]))
            result[hp_mode]={'confusion':dict(confusion),'mean_wait_probability':sum(prob)/len(prob)}
        report[group]={'states':len(states),'interventions':result}
    write(root/'wait-health-diagnosis.json',report);print(json.dumps(report,indent=2))

if __name__=='__main__':main()
