"""Synthetic L corridor, using the corpus's exact native LOS ray definition."""
import collections
import json
import struct
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
LENGTHS=[4,8,16,24]

def xy(x,y,g):
    if g>=4:x=-x
    for _ in range(g%4):x,y=-y,x
    return x+40,y+35

def generate(folder):
    folder.mkdir(parents=True,exist_ok=True)
    lines=iter((ROOT/'fixtures/native-1057.rays').read_text().splitlines())
    ends=[tuple(map(int,next(lines).split())) for _ in range(int(next(lines)))];blockers=[]
    for line in lines:
        x,y,inside,bits=line.split()
        if int(inside):blockers.append((int(x),int(y),int(bits[::-1],2)))
    allowed={(x,y) for x,y,_ in blockers}
    steps=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]
    manifest=[]
    for length in LENGTHS:
        for group in range(8):
            mid=len(manifest);floor=np.zeros(5600,np.uint8)
            for x,y in [(x,0) for x in range(-length,15)]+[(-length,y) for y in range(-20,1)]:
                px,py=xy(x,y,group);floor[py*80+px]=1
            # Disconnected, invisible reset-only rooms ensure the unmodified
            # terminal autoreset can place its ordinary40 spawn slots/3 stairs.
            for ox in [3,69]:
                for oy in [3,59]:
                    for x in range(ox,ox+8):
                        for y in range(oy,oy+8):floor[y*80+x]=1
            cells=np.flatnonzero(floor);index=np.full(5600,-1,np.int16);index[cells]=np.arange(len(cells))
            ds=np.full((len(cells),5600),65535,np.uint16)
            for j,p in enumerate(cells):
                ds[j,p]=0;queue=collections.deque([int(p)])
                while queue:
                    p=queue.popleft()
                    for dx,dy in steps:
                        x,y=p%80+dx,p//80+dy
                        if 0<=x<80 and 0<=y<70:
                            q=y*80+x
                            if floor[q] and ds[j,q]==65535:ds[j,q]=ds[j,p]+1;queue.append(q)
            masks=np.zeros((5600,10),np.uint32)
            for p in cells:
                px,py=p%80,p//80;seen=1<<144
                for sx,sy in [(1,1),(-1,1),(-1,-1),(1,-1)]:
                    dead=0
                    for x,y,bits in blockers:
                        qx,qy=px+sx*x,py+sy*y
                        if 0<=qx<80 and 0<=qy<70 and not floor[qy*80+qx]:dead|=bits
                    for i,(x,y) in enumerate(ends):
                        qx,qy=px+sx*x,py+sy*y
                        if not(dead>>i)&1 and 0<=qx<80 and 0<=qy<70 and (x,y) in allowed:seen|=1<<((sy*y+8)*17+sx*x+8)
                masks[p]=[(seen>>(32*i))&0xffffffff for i in range(10)]
            padded=np.full(5600,-1,np.int16);padded[:len(cells)]=cells
            with (folder/f'map-{mid:03d}.bin').open('wb') as f:
                f.write(struct.pack('<3I4i',0x44325650,mid,len(cells),18,681,794,906))
                for a in [floor,padded,index,ds,masks]:f.write(a.tobytes())
            manifest.append(dict(map=mid,backtrack=length,symmetry=group))
    (folder/'manifest.json').write_text(json.dumps(manifest,indent=2));return manifest
