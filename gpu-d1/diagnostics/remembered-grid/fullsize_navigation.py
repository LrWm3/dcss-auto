"""80x70 navigation fixtures from existing disjoint native D1 corpus splits.

The precomputed distances construct scenarios only. The policy receives the
same local crop and coarse remembered map, with no path or frontier hints.
"""
import hashlib,json,struct,subprocess
from pathlib import Path
import numpy as np
from run import save_json
from runtime import Env,OUT,ROOT,HERE,old

FOLDER=OUT/'fullsize-navigation'
DIRS=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]

def read_map(path):
 with path.open('rb') as f:
  magic,seed,n=struct.unpack('<3I',f.read(12));assert magic==0x44325650
  f.read(16)
  floor=np.frombuffer(f.read(5600),np.uint8).copy()
  cells=np.frombuffer(f.read(11200),np.int16).copy()
  index=np.frombuffer(f.read(11200),np.int16).copy()
  distance=np.frombuffer(f.read(n*5600*2),np.uint16).reshape(n,5600).copy()
  los=np.frombuffer(f.read(5600*10*4),np.uint32).reshape(5600,10).copy()
  assert not f.read(1)
 return floor,cells,index,distance,los


def generate():
 FOLDER.mkdir(exist_ok=True);maps=FOLDER/'maps';maps.mkdir(exist_ok=True)
 if (maps/'manifest.json').exists():return
 seen=set();manifest={}
 for split,count,seed in [('train',64,41201),('validation',16,41202),('test',32,41203)]:
  source=ROOT/'fixtures/d1-corpus-388'/split
  records=json.loads((source/'manifest.json').read_text())['maps']
  rng=np.random.default_rng(seed);chosen=rng.choice(len(records),count,replace=False)
  arrays=[];scenarios=[];provenance=[]
  for mid,j in enumerate(chosen):
   rec=records[int(j)];path=source/rec['file'];a=read_map(path);floor,cells,index,dist,los=a
   digest=hashlib.sha256(floor.tobytes()).hexdigest();assert digest not in seen;seen.add(digest)
   n=len(dist);arrays.append(a);validcells=cells[:n]
   for trial in range(4):
    start=int(rng.integers(n));candidates=np.where((dist[start,validcells]>=24)&(dist[start,validcells]<=128))[0]
    assert len(candidates), (path,start)
    goal=int(rng.choice(candidates));target=int(cells[goal]);player=int(cells[start])
    # A real traversed history from a stair to the player creates remembered goals.
    history=[target];current=target
    while current!=player:
     x,y=current%80,current//80
     options=[(y+dy)*80+x+dx for dx,dy in DIRS if 0<=x+dx<80 and 0<=y+dy<70]
     current=next(q for q in options if floor[q] and dist[start,q]+1==dist[start,current])
     history.append(current)
    assert len(history)<=129
    stairs=[int(cells[k]) for k in np.argsort(dist[goal,validcells])[:3]]
    for kind in (0,1):
     hist=history if kind==0 else [player]
     row=[mid,kind,player,*stairs,-1,len(hist),*hist]
     scenarios.append(row+[-1]*(264-len(row)))
   provenance.append(dict(seed=rec['seed'],source=str(path.relative_to(ROOT)),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),geometry_sha256=digest,cells=n))
  nc=np.array([len(a[3]) for a in arrays],np.int32)
  np.savez_compressed(maps/f'{split}.npz',floor=np.stack([a[0] for a in arrays]),cells=np.stack([a[1] for a in arrays]),index=np.stack([a[2] for a in arrays]),distance=np.concatenate([a[3] for a in arrays]),los=np.stack([a[4] for a in arrays]),ncells=nc,offsets=np.r_[0,np.cumsum(nc[:-1])].astype(np.int32),scenarios=np.array(scenarios,np.int32))
  manifest[split]=provenance;print(split,count,'maps prepared',flush=True)
 save_json(maps/'manifest.json',manifest)


def build_full():
 generate();source=HERE/'native.cu';library=FOLDER/'grid-full.so'
 signature=hashlib.sha256(source.read_bytes()+(HERE.parent/'d1-stat-generalization/learn.cu').read_bytes()+(ROOT/'branches/d1-stairs-v2/src/sim.h').read_bytes()).hexdigest()
 stamp=FOLDER/'build.json'
 if not library.exists() or not stamp.exists() or json.loads(stamp.read_text())!=signature:
  subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*old.FLAGS,'-DCLUMP_MODE=0','-DFULLSIZE_NAV',str(source),'-o',str(library)],check=True)
  save_json(stamp,signature)
 return library


class FullEnv(Env):
 def __init__(self,split='train',batch=128):
  super().__init__(split,batch,map_dir=FOLDER/'maps',grid_shape=(70,80),library=FOLDER/'grid-full.so')
 def reset(self,ids=None,seed=0,kinds=(0,1),labels=True):
  return super().reset(ids,seed,kinds,labels)

if __name__=='__main__':generate()
