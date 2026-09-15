"""Small loop/pillar scenarios with disjoint geometry and a static safe detour.
Writes the resident-map format; LOS is unused by this toy task and zero-filled.
"""
import collections,hashlib,json,pathlib,random,struct
import numpy as np
W,H,N=80,70,5600
ROOT=pathlib.Path(__file__).resolve().parents[1]
DELTAS=((0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1))
def neighbors(p,floor):
 x,y=p%W,p//W
 for dx,dy in DELTAS:
  xx,yy=x+dx,y+dy
  if 0<=xx<W and 0<=yy<H and floor[yy*W+xx]:yield yy*W+xx

def generate(seed,family):
 r=random.Random(seed);w=r.randint(16,23);h=r.randint(12,18);ox=r.randint(5,50);oy=r.randint(5,42)
 floor=np.zeros(N,dtype=np.uint8)
 # A ring around a solid obstacle, with varied corridor width and offsets.
 thickness=2 if family=='loop_detour' else r.randint(3,5)
 for y in range(h):
  for x in range(w):
   if x<thickness or x>=w-thickness or y<thickness or y>=h-thickness:floor[(oy+y)*W+ox+x]=1
 p=(oy+2)*W+ox+1;q=(oy+1)*W+ox+w//2;s=(oy+2)*W+ox+w-2
 # Reflections and translations prevent a fixed left/right direction cue.
 if r.randrange(2):
  floor=floor.reshape(H,W)[:,::-1].copy().reshape(-1)
  p,q,s=[z//W*W+W-1-z%W for z in (p,q,s)]
 if r.randrange(2):
  floor=floor.reshape(H,W)[::-1].copy().reshape(-1)
  p,q,s=[(H-1-z//W)*W+z%W for z in (p,q,s)]
 safe=floor.copy()
 for z in np.flatnonzero(safe):
  if max(abs(int(z)%W-q%W),abs(int(z)//W-q//W))<=2:safe[z]=0
 queue=collections.deque([p]);seen={p}
 while queue:
  for z in neighbors(queue.popleft(),safe):
   if z not in seen:seen.add(z);queue.append(z)
 assert s in seen,'No static detour around ogre exclusion zone'
 return floor,dict(player=p,ogre=q,monster=s,awake=seed%2,energy=70+5*((seed//40)%2),family=family,seed=seed,static_safe_path=True)

def write_map(path,floor,meta):
 cells=np.flatnonzero(floor).astype('<i2');index=np.full(N,-1,dtype='<i2');index[cells]=np.arange(len(cells))
 dist=np.full((len(cells),N),65535,dtype='<u2')
 adjacency={int(p):list(neighbors(int(p),floor)) for p in cells}
 for i,p in enumerate(cells):
  dist[i,p]=0;queue=collections.deque([int(p)])
  while queue:
   p=queue.popleft()
   for q in adjacency[p]:
    if dist[i,q]==65535:dist[i,q]=dist[i,p]+1;queue.append(q)
 padded=np.full(N,-1,dtype='<i2');padded[:len(cells)]=cells
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('wb') as f:
  f.write(struct.pack('<3I4i',0x44325650,meta['seed'],len(cells),20,0,0,0))
  for a in (floor,padded,index,dist,np.zeros((N,10),dtype='<u4')):f.write(a.tobytes())
 meta['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();meta['geometry_sha256']=hashlib.sha256(floor.tobytes()).hexdigest()
 path.with_suffix('.json').write_text(json.dumps(meta,indent=2)+'\n')

def canonical(floor):
 m=floor.reshape(H,W);ys,xs=np.nonzero(m);m=m[ys.min():ys.max()+1,xs.min():xs.max()+1]
 return min(str(a.shape).encode()+a.tobytes() for b in (m,m.T) for a in (b,b[::-1],b[:,::-1],b[::-1,::-1]))

def main():
 root=ROOT/'fixtures/pressure';seen=set();allrows=[]
 for split,count,base in [('train',32,800000),('validation',16,900000)]:
  rows=[]
  for i in range(count):
   family=('loop_detour','wide_pillar')[i%2];seed=base+i*10+(i//2)%2
   while True:
    floor,meta=generate(seed,family);sha=hashlib.sha256(canonical(floor)).hexdigest()
    if sha not in seen:break
    seed+=1000
   seen.add(sha);meta['canonical_geometry_sha256']=sha;meta['split']=split;meta['scenario_id']=f'{split}-{i:03d}';meta['label']='ogre_pressure'
   write_map(root/split/f'map-{seed}.bin',floor,meta);rows.append(meta)
  (root/split/'manifest.json').write_text(json.dumps(rows,indent=2)+'\n');allrows+=rows
 (root/'manifest.json').write_text(json.dumps(dict(format='pressure-v1',scenarios=allrows,labels_are_policy_inputs=False),indent=2)+'\n')
 print(f'Wrote {len(allrows)} scenarios with unique geometry and static detours to {root}')
if __name__=='__main__':main()
