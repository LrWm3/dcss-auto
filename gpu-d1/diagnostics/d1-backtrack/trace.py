"""Trace representative greedy strong-enemy trajectories; no policy changes."""
import ctypes as C
import json
import torch
from run import Env,OUT,r,LENGTHS
from maps import xy

@torch.no_grad()
def main():
    torch.set_num_threads(1);e=Env(reps=1);m=r.load_model(r.SUITE/'varied/checkpoints/5000192.pt');e.setup();rows=[]
    for tick in range(48):
        z=e.measure().cpu();d=m(e.obs,e.mask)[0];a=d.greedy();p=d.probs.cpu();o=e.obs.cpu()
        for length_index,b in enumerate(LENGTHS):
            i=length_index*24+2
            cue=o[i,725:733];direction=int(cue.argmax()) if cue.sum()>0 else -1
            rows.append(dict(step=tick,backtrack=b,x=int(z[i,0]),y=int(z[i,1]),visible_enemy=bool(o[i,450:650].reshape(40,5)[:,4].any()),frontier_direction=direction,frontier_distance=float(o[i,721]*150),frontier_dx=float(o[i,719]*80),frontier_dy=float(o[i,720]*70),action=int(a[i]),wait_probability=float(p[i,16]),move_probabilities=p[i,:8].tolist()))
        e.step(a)
    (OUT/'trace.json').write_text(json.dumps(rows,indent=2))
    # Identical movement history, differing only in the enemy behind us.
    e.setup();directions=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]
    actions=[]
    for case in range(96):
        g=(case//3)%8;p=xy(0,0,g);q=xy(-1,0,g)
        actions.append(directions.index((q[0]-p[0],q[1]-p[1])))
    e.step(torch.tensor(actions,device='cuda',dtype=torch.long))
    identical=[]
    for mid in range(32):
        i=mid*3
        assert torch.equal(e.obs[i],e.obs[i+2]) and torch.equal(e.mask[i],e.mask[i+2])
        identical.append(mid)
    (OUT/'observation-aliasing.json').write_text(json.dumps(dict(identical_map_pairs=identical,comparison='No enemy versus strong sleeper after the same single backward move; complete observations and masks are byte-identical.')))
    for b in LENGTHS:
        print('distance',b)
        for x in [v for v in rows if v['backtrack']==b][:28]:print({k:x[k] for k in ['step','x','y','visible_enemy','frontier_direction','action']})

if __name__=='__main__':main()
