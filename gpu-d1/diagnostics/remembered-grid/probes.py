"""Paired goal tests: identical local observation and walked history, different distant stairs."""
import hashlib,json
import numpy as np
import torch
from maps import encode,G,X0,Y0
from runtime import OUT,Env,Policy,SpatialPolicy

def generate(split='probe'):
    rng=np.random.default_rng(118122 if split=='probe' else 219155);arrays=[];scenes=[];records=[]
    for j in range(24):
        left,right=map(int,rng.integers(10,15,size=2));cx=16;cy=int(rng.integers(13,19));a=np.zeros((32,32),np.uint8);a[cy,cx-left:cx+right+1]=1
        # Optional branch makes varying geometry without revealing the goal locally.
        if j%2:a[cy-int(rng.integers(4,10)):cy+1,cx]=1
        group=j%8
        def tr(x,y):
            if group>=4:x=31-x
            for _ in range(group%4):x,y=31-y,x
            return (Y0+y)*80+X0+x
        b=np.zeros_like(a)
        for y,x in zip(*np.nonzero(a)):
            p=tr(int(x),int(y));b[p//80-Y0,p%80-X0]=1
        arrays.append(encode(b)[:5]);history=[tr(x,cy) for x in range(cx-left,cx+right+1)]+[tr(x,cy) for x in range(cx+right-1,cx-1,-1)]
        for side in [-1,1]:
            distance=left if side<0 else right;stairs=[tr(cx+side*(distance-k),cy) for k in range(3)]
            row=[j,0,tr(cx,cy),*stairs,-1,len(history),*history];scenes.append(row+[-1]*(264-len(row)))
        records.append(dict(map=j,left=left,right=right,symmetry=group,sha256=hashlib.sha256(b.tobytes()).hexdigest()))
    nc=np.array([len(x[3]) for x in arrays],np.int32);off=np.r_[0,np.cumsum(nc[:-1])].astype(np.int32)
    np.savez(OUT/'maps'/f'{split}.npz',floor=np.stack([x[0] for x in arrays]),cells=np.stack([x[1] for x in arrays]),index=np.stack([x[2] for x in arrays]),distance=np.concatenate([x[3] for x in arrays]),los=np.stack([x[4] for x in arrays]),ncells=nc,offsets=off,scenarios=np.array(scenes,np.int32))
    return records

@torch.no_grad()
def evaluate(model,split='probe',intervene=None):
    e=Env(split,48);e.reset(torch.arange(48,device='cuda'),seed=127)
    logits=model(e.grid,e.mask,e.stats,intervene);actions=logits.argmax(-1);expected=e.labels.clone();correct=actions==expected
    # Directly verify identical local sensor/memory crops and player stats.
    for j in range(0,48,2):
        x,y=e.stats[j,2:4].int().tolist()
        assert torch.equal(e.grid[j,:,y-7:y+8,x-7:x+8],e.grid[j+1,:,y-7:y+8,x-7:x+8])
        assert torch.equal(e.stats[j],e.stats[j+1]);assert torch.equal(e.mask[j],e.mask[j+1]);assert expected[j]!=expected[j+1]
    result=dict(initial_correct=float(correct.float().mean()),both_in_pair_correct=int(correct.reshape(-1,2).all(1).sum()),pairs=24,actions=actions.tolist(),teacher_actions=expected.tolist())
    outcomes=torch.zeros(48,device='cuda');turns=outcomes.clone();initial=e.stats[:,1]*2048
    for tick in range(256):
        active=e.active.clone();actions=model(e.grid,e.mask,e.stats,intervene).argmax(-1);e.step(actions,limit=256,labels=False)
        end=active&~e.active;outcomes[end]=e.out[end,2];turns[end]=e.out[end,5]-initial[end]
        if not e.active.any():break
    result.update(exit=float(outcomes.mean()),turns=float(turns.mean()));return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--folder',default='memory-spatial');p.add_argument('--split',default='probe');args=p.parse_args();torch.set_num_threads(1)
    generate(args.split);folder=OUT/args.folder;ck=torch.load(folder/('best.pt' if (folder/'best.pt').exists() else 'latest.pt'),weights_only=False)
    model=(SpatialPolicy if ck.get('architecture')=='spatial' else Policy)(ck['arm']).cuda();model.load_state_dict(ck['model'])
    out={key:evaluate(model,args.split,value) for key,value in [('normal',None),('global_removed','erase_global')]}
    (folder/(args.split+'.json')).write_text(json.dumps(out,indent=2));print(json.dumps(out))
