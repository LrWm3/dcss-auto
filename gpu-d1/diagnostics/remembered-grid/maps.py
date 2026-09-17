"""Disjoint procedural navigation fixtures; native DCSS LOS and 8-way geometry."""
import hashlib,json
from pathlib import Path
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import shortest_path
ROOT=Path(__file__).resolve().parents[2]
G=32; X0=24; Y0=19; N=5600
DIRS=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]

def geometry(seed,long=False):
    r=np.random.default_rng(seed); k=6 if long else int(r.integers(4,6)); step=5
    a=np.zeros((32,32),np.uint8); seen={(0,0)};stack=[(0,0)];edges=[]
    while stack:
        x,y=stack[-1]; opts=[(x+dx,y+dy) for dx,dy in DIRS[:4] if 0<=x+dx<k and 0<=y+dy<k and (x+dx,y+dy) not in seen]
        if not opts:stack.pop();continue
        q=opts[int(r.integers(len(opts)))];edges.append(((x,y),q));seen.add(q);stack.append(q)
    for _ in range(int(r.integers(0,4))):
        x,y=r.integers(k,size=2);dx,dy=DIRS[int(r.integers(4))];q=(x+dx,y+dy)
        if 0<=q[0]<k and 0<=q[1]<k:edges.append(((x,y),q))
    for (x,y),(u,v) in edges:
        x,y,u,v=3+x*step,3+y*step,3+u*step,3+v*step
        a[min(y,v):max(y,v)+1,min(x,u):max(x,u)+1]=1
    for y in range(k):
        for x in range(k):
            if r.random()<.55:
                px,py=3+x*step,3+y*step;a[py-1:py+2,px-1:px+2]=1
                if r.random()<.4:a[py-1,px-1]=0
    a=np.rot90(a,int(r.integers(4)))
    if r.random()<.5:a=a[:,::-1]
    return a.copy()

def native_los(floor,cells):
    lines=iter((ROOT/'fixtures/native-1057.rays').read_text().splitlines())
    ends=[tuple(map(int,next(lines).split())) for _ in range(int(next(lines)))]; blockers=[]
    for line in lines:
        x,y,inside,bits=line.split()
        if int(inside):blockers.append((int(x),int(y),int(bits[::-1],2)))
    allowed={(x,y) for x,y,_ in blockers};masks=np.zeros((N,10),np.uint32)
    for p in cells:
        px,py=int(p)%80,int(p)//80;bits=1<<144
        for sx,sy in [(1,1),(-1,1),(-1,-1),(1,-1)]:
            dead=0
            for x,y,b in blockers:
                qx,qy=px+sx*x,py+sy*y
                if not(0<=qx<80 and 0<=qy<70) or not floor[qy*80+qx]:dead|=b
            for i,(x,y) in enumerate(ends):
                qx,qy=px+sx*x,py+sy*y
                if not(dead>>i)&1 and 0<=qx<80 and 0<=qy<70 and (x,y) in allowed:bits|=1<<((sy*y+8)*17+sx*x+8)
        masks[p]=[(bits>>(32*i))&0xffffffff for i in range(10)]
    return masks

def encode(a):
    full=np.zeros((70,80),np.uint8);full[Y0:Y0+G,X0:X0+G]=a;floor=full.ravel();cells=np.flatnonzero(floor).astype(np.int16)
    index=np.full(N,-1,np.int16);index[cells]=np.arange(len(cells));rows=[];cols=[]
    for j,p in enumerate(cells):
        x,y=int(p)%80,int(p)//80
        for dx,dy in DIRS:
            q=(y+dy)*80+x+dx
            if floor[q]:rows.append(j);cols.append(int(index[q]))
    graph=csr_matrix((np.ones(len(rows)),(rows,cols)),shape=(len(cells),len(cells)))
    ds,pred=shortest_path(graph,directed=False,unweighted=True,return_predecessors=True)
    assert np.isfinite(ds).all()
    distance=np.full((len(cells),N),65535,np.uint16);distance[:,cells]=ds.astype(np.uint16)
    padded=np.full(N,-1,np.int16);padded[:len(cells)]=cells
    return floor,padded,index,distance,native_los(floor,cells),ds,pred,cells

def route(cells,pred,start,end):
    p=int(end);out=[int(cells[p])]
    while p!=start:p=int(pred[start,p]);assert p>=0;out.append(int(cells[p]))
    return out[::-1]

def generate(out):
    out.mkdir(parents=True,exist_ok=True)
    if (out/'manifest.json').exists():return
    allhash=set();manifest={}
    for split,count,offset,long in [('train',128,711000,False),('validation',32,812000,False),('test',64,913000,False),('long',32,1014000,True)]:
        arrays=[];scenarios=[];records=[]
        for j in range(count):
            a=geometry(offset+j,long);h=hashlib.sha256(a.tobytes()).hexdigest();assert h not in allhash;allhash.add(h)
            floor,padded,index,distance,los,ds,pred,cells=encode(a);arrays.append((floor,padded,index,distance,los))
            r=np.random.default_rng(offset+j+91)
            for trial in range(4):
                start=int(r.integers(len(cells))); opts=np.flatnonzero(ds[start]>=max(12,ds[start].max()*.65));goal=int(r.choice(opts))
                near=np.argsort(ds[goal])[:3];stairs=[int(cells[z]) for z in near]
                hist=route(cells,pred,goal,start)
                assert len(hist)<=256
                for kind in [0,1]:
                    history=hist if kind==0 else [int(cells[start])]
                    row=[j,kind,int(cells[start]),*stairs,-1,len(history),*history]
                    scenarios.append(row+[-1]*(264-len(row)))
            records.append(dict(map=j,seed=offset+j,sha256=h,cells=len(cells)))
        # Independent, variable T / L junction pressure cases. Genuine observed
        # history runs from the junction toward a visible sleeper seven away.
        for j in range(32):
            attempt=0
            while True:
                r=np.random.default_rng(offset+9900+j+attempt*113);length=int(r.choice(([4,6,8,10] if split=='train' else [5,7] if split=='validation' else [9,11]) if not long else [12,14]));arm=int(r.integers(10,15));a=np.zeros((32,32),np.uint8)
                cx=8 if long else 12;cy=16
                a[cy,cx:cx+length+8]=1;a[cy-arm:cy+1,cx]=1
                if j%2:a[cy:cy+int(r.integers(4,10)),cx]=1
                group=j%8
                def transform(x,y):
                    if group>=4:x=31-x
                    for _ in range(group%4):x,y=31-y,x
                    return (Y0+y)*80+X0+x
                b=np.zeros_like(a)
                for y,x in zip(*np.nonzero(a)):
                    p=transform(int(x),int(y));b[p//80-Y0,p%80-X0]=1
                h=hashlib.sha256(b.tobytes()).hexdigest();attempt+=1
                if h not in allhash:allhash.add(h);break
            mid=len(arrays);enc=encode(b);arrays.append(enc[:5]);history=[transform(x,cy) for x in range(cx,cx+length+1)]
            stairs=[transform(cx,cy-arm+k) for k in range(3)];enemy=transform(cx+length+7,cy)
            # For long fixtures fit both segments by shifting the junction.
            row=[mid,2,history[-1],*stairs,enemy,len(history),*history]
            scenarios.append(row+[-1]*(264-len(row)))
            records.append(dict(map=mid,pressure=True,backtrack=length,symmetry=group,sha256=h))
        nc=np.array([len(x[3]) for x in arrays],np.int32);off=np.r_[0,np.cumsum(nc[:-1])].astype(np.int32)
        np.savez(out/f'{split}.npz',floor=np.stack([x[0] for x in arrays]),cells=np.stack([x[1] for x in arrays]),index=np.stack([x[2] for x in arrays]),distance=np.concatenate([x[3] for x in arrays]),los=np.stack([x[4] for x in arrays]),ncells=nc,offsets=off,scenarios=np.array(scenarios,np.int32))
        manifest[split]=records;print('maps',split,len(arrays),flush=True)
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2))
