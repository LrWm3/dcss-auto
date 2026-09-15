"""Evaluate spatial-policy checkpoints on the matched fresh suite."""
import argparse,json,pathlib,torch
from train_sleep_spatial import Policy,Env
from train_clear import evaluate

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('run',type=pathlib.Path)
    ap.add_argument('--output',required=True,type=pathlib.Path)
    ap.add_argument('--episodes',type=int,default=2048)
    ap.add_argument('--seed',type=int,default=1200000)
    args=ap.parse_args()
    torch.set_num_threads(1)
    env=Env(args.episodes,8,seed=args.seed)
    rows=[]
    for folder in sorted(args.run.glob('seed-*')):
        for path in sorted(folder.glob('policy-*.pt'),key=lambda p:int(p.stem.split('-')[1])):
            steps=int(path.stem.split('-')[1])
            if steps<10000000: continue
            model=Policy().cuda()
            model.load_state_dict(torch.load(path,map_location='cuda',weights_only=False)['model']); model.eval()
            for mode in ('sampled','greedy'):
                row=evaluate(env,model,mode,args.seed)
                row.update(policy=folder.name,checkpoint=str(path),decisions=steps)
                rows.append(row); print(json.dumps(row),flush=True)
    args.output.write_text(json.dumps(rows,indent=2)+'\n')
if __name__=='__main__': main()
