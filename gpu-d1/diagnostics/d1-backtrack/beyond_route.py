"""A fixed detour feasibility witness; does not control policy evaluations."""
import argparse
import json
import torch
import beyond
from maps import xy

@torch.no_grad()
def main():
    p=argparse.ArgumentParser();p.add_argument('--awake',action='store_true');args=p.parse_args()
    beyond.configure(args.awake,True);torch.set_num_threads(1);e=beyond.Env(awake=args.awake);e.setup()
    actions=[];directions=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]
    for case in range(96):
        distance=[4,8,16,24][case//24];g=case//3%8
        points=[(0,0),(1,0),(2,0),(3,0),(4,-1),(5,-2),(6,-2),(7,-2),(8,-2),(9,-1),(10,0)]+[(x,0) for x in range(11,8+distance)]
        route=[]
        for a,b in zip(points,points[1:]):
            a=xy(*a,g);b=xy(*b,g);route.append(directions.index((b[0]-a[0],b[1]-a[1])))
        actions.extend([route+[18]*(40-len(route))]*e.reps)
    planned=torch.tensor(actions,device='cuda');active=torch.ones(e.batch,device='cuda',dtype=torch.bool);terminal=torch.zeros(e.batch,4,device='cuda');woke=torch.zeros_like(active)
    for tick in range(40):
        woke|=active&e.measure()[:,2].bool()
        e.step(planned[:,tick].contiguous(),active=active);end=active&e.out[:,1].bool();terminal[end]=e.out[end][:,[2,6,3,49]];active&=~end
    rows=[]
    for case in range(96):
        z=terminal[case*e.reps:(case+1)*e.reps]
        rows.append(dict(stairs_beyond_enemy=[4,8,16,24][case//24],symmetry=case//3%8,enemy=['none','weak','strong'][case%3],episodes=e.reps,exits_with_enemy_awake=int(((z[:,0]>0)&woke[case*e.reps:(case+1)*e.reps]).sum()),unfinished=int(active[case*e.reps:(case+1)*e.reps].sum()),exits=int(z[:,0].sum()),deaths=int(z[:,1].sum()),kills=int(z[:,2].sum()),mean_damage=float(z[:,3].mean())))
    report=dict(description='Fixed 10-step arc through widened room, then straight to stairs; no attack actions. Feasibility witness only, not policy intervention.',strong_starts_awake=args.awake,rows=rows)
    (beyond.OUT/'detour-witness.json').write_text(json.dumps(report,indent=2)+'\n')
    for enemy in ['none','weak','strong']:
        a=[x for x in rows if x['enemy']==enemy];print(enemy,{k:sum(x[k] for x in a) for k in ['exits','deaths','kills','unfinished','exits_with_enemy_awake']},'damage',sum(x['mean_damage'] for x in a)/32)
if __name__=='__main__':main()
