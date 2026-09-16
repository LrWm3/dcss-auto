import collections,hashlib,pathlib,struct
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[3]
def compile_map(spec,path,seed):
    floor=np.zeros(5600,np.uint8)
    for x,y in spec['floor']:floor[(35+y)*80+40+x]=1
    cells=np.flatnonzero(floor);index=np.full(5600,-1,np.int16);index[cells]=np.arange(len(cells))
    distances=np.full((len(cells),5600),65535,np.uint16)
    directions=[(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)]
    for j,origin in enumerate(cells):
        distances[j,origin]=0;q=collections.deque([origin])
        while q:
            p=q.popleft()
            for dx,dy in directions:
                x,y=p%80+dx,p//80+dy
                if 0<=x<80 and 0<=y<70:
                    dest=y*80+x
                    if floor[dest] and distances[j,dest]==65535:distances[j,dest]=distances[j,p]+1;q.append(dest)
    lines=iter((ROOT/'fixtures/native-1057.rays').read_text().splitlines());ends=[tuple(map(int,next(lines).split())) for _ in range(int(next(lines)))];blockers=[]
    for line in lines:
        x,y,inside,bits=line.split()
        if int(inside):blockers.append((int(x),int(y),int(bits[::-1],2)))
    valid_x={x for x,y,bits in blockers};masks=np.zeros((5600,10),np.uint32)
    for p in cells:
        px,py=p%80,p//80;seen=1<<144
        for sx,sy in [(1,1),(-1,1),(-1,-1),(1,-1)]:
            dead=0
            for x,y,bits in blockers:
                qx,qy=px+sx*x,py+sy*y
                if 0<=qx<80 and 0<=qy<70 and not floor[qy*80+qx]:dead|=bits
            for i,(x,y) in enumerate(ends):
                qx,qy=px+sx*x,py+sy*y
                if not(dead>>i)&1 and 0<=qx<80 and 0<=qy<70 and x in valid_x:seen|=1<<((sy*y+8)*17+sx*x+8)
        masks[p]=[(seen>>(32*i))&0xffffffff for i in range(10)]
    padded=np.full(5600,-1,np.int16);padded[:len(cells)]=cells
    with path.open('wb') as f:
        f.write(struct.pack('<3I4i',0x44325650,seed,len(cells),18,681,794,906))
        for a in [floor,padded,index,distances,masks]:f.write(a.tobytes())
    return hashlib.sha256(floor.tobytes()).hexdigest()
