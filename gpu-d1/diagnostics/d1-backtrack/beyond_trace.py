"""Record first 32 greedy steps for the canonical strong-enemy orientation."""
import argparse
import json
import torch
import beyond
from beyond import Env,ROOT,r

@torch.no_grad()
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--awake',action='store_true');parser.add_argument('--passable',action='store_true');args=parser.parse_args();beyond.configure(args.awake,args.passable)
    torch.set_num_threads(1);e=Env(reps=1,awake=args.awake);rows=[]
    paths={'source5m':r.SUITE/'varied/checkpoints/5000192.pt','control6m':ROOT/'learning-runs/d1-sleeper-bypass/control/checkpoints/1000448.pt','practice6m':ROOT/'learning-runs/d1-sleeper-bypass/practice/checkpoints/1000448.pt'}
    for name,path in paths.items():
        m=r.load_model(path);e.setup();active=torch.ones(e.batch,device='cuda',dtype=torch.bool)
        for tick in range(32):
            z=e.measure().cpu();d=m(e.obs,e.mask)[0];a=d.greedy();p=d.probs.cpu();o=e.obs.cpu()
            for j,distance in enumerate([4,8,16,24]):
                i=j*24+2
                if not active[i]:continue
                rows.append(dict(model=name,step=tick,stairs_beyond_enemy=distance,x=int(z[i,0]),y=int(z[i,1]),awake=bool(z[i,2]),visible_enemy=bool(o[i,450:650].reshape(40,5)[:,4].any()),hp_fraction=float(o[i,650]),action=int(a[i]),wait_probability=float(p[i,16]),move_probabilities=p[i,:8].tolist()))
            e.step(a,active=active);active&=~e.out[:,1].bool()
    (beyond.OUT/'trace.json').write_text(json.dumps(rows,indent=2)+'\n')
    for name in paths:
        for distance in [4,8,16,24]:
            a=[v for v in rows if v['model']==name and v['stairs_beyond_enemy']==distance]
            print(name,distance,[(v['x'],v['action'],round(v['wait_probability'],3)) for v in a[:12]])
if __name__=='__main__':main()
