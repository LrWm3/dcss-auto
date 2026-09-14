"""Audit teacher labels and neural scores without changing training data."""
import os
os.environ['DCSS_REPRESENTATION']='spatial-v6'
import argparse
import json
from collections import Counter
from pathlib import Path
import torch
from bootstrap_repair import read_training, write
from model import load_model, tensor_for_actions
from teacher import choose_action, _actions

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);args=p.parse_args()
    torch.set_num_threads(1);root=args.root
    model,_=load_model(root/'round-02/model.pt')
    report={'labels':{},'cutoffs':[]}
    for folder in [root/'demonstrations',*sorted(root.glob('round-*/corrections'))]:
        rows=read_training(folder,limit=256);counts=Counter();mismatch=0;confusion=Counter()
        for row in rows:
            s=row['observation'];a=_actions(s);label=row['teacher_action_index']
            counts[a[label]['kind']]+=1;mismatch+=int(label!=choose_action(s))
            with torch.no_grad():pred=int(model(tensor_for_actions(s,a)).argmax())
            confusion[a[label]['kind']+' -> '+a[pred]['kind']]+=1
        report['labels'][str(folder.relative_to(root))]={'sampled':len(rows),'teacher_kinds':dict(counts),
            'recomputed_label_mismatches':mismatch,'confusion':dict(confusion)}
    for f in sorted(root.glob('round-*/validation/results.json')):
        for result in json.loads(f.read_text()):
            s=json.loads((Path(result['resume_checkpoint'])/'case.json').read_text())['observation']
            a=_actions(s);label=choose_action(s)
            with torch.no_grad():scores=model(tensor_for_actions(s,a))
            ranking=sorted(range(len(a)),key=lambda i:float(scores[i]),reverse=True)
            report['cutoffs'].append({'round':f.parts[-3],'seed':result['seed'],
                'hp':s['player']['hp'],'max_hp':s['player']['max_hp'],'teacher':a[label],
                'top_actions':[{'action':a[i],'score':float(scores[i])} for i in ranking[:3]]})
    write(root/'label-audit.json',report);print(json.dumps(report,indent=2))

if __name__=='__main__':main()
