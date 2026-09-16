"""Disjoint layouts for target selection and visible sleeping-enemy recovery."""
import json,shutil,struct,hashlib
from assets import ASSETS
from map_compile import compile_map

def rotate(p,g):
 x,y=p
 if g//4:x=-x
 for _ in range(g%4):x,y=-y,x
 return [x,y]

def specifications(task,split):
 out=[]
 for variant in range(2):
  for g in range(8):
   if task=='target':
    w=(2+variant) if split=='train' else (4+variant)
    floor={(x,y) for x in range(-w,w+1) for y in range(-2,3)}
    enemies=[[1,0],[-1,0] if variant==0 else [0,1]]
   else:
    w=(1+variant) if split=='train' else (3+variant)
    floor={(x,y) for x in range(-2,10) for y in range(-w,w+1)}
    enemies=[[7,0],[7,0]]
   out.append(dict(task=task,split=split,group=g,variant=variant,player=[0,0],enemies=[rotate(p,g) for p in enemies],floor=sorted(rotate(p,g) for p in floor)))
 return out

def main():
 ASSETS.mkdir(parents=True,exist_ok=True);hashes={};cache={}
 for task in ['target','sleep']:
  for split in ['train','heldout']:
   folder=ASSETS/task/split;folder.mkdir(parents=True,exist_ok=True);rows=specifications(task,split);key=task+'/'+split;hashes[key]=[]
   for i,spec in enumerate(rows):
    signature=json.dumps(spec['floor']);path=folder/f'map-{i}.bin'
    if signature in cache:
     source,h=cache[signature];shutil.copyfile(source,path)
     with path.open('r+b') as f:f.seek(4);f.write(struct.pack('<I',i))
    else:
     h=compile_map(spec,path,i);cache[signature]=(path,h)
    hashes[key].append(h)
   (folder/'scenarios.json').write_text(json.dumps(rows)+'\n')
  assert not set(hashes[task+'/train'])&set(hashes[task+'/heldout'])
 (ASSETS/'geometry-checks.json').write_text(json.dumps(dict(hashes=hashes,disjoint=True,maps_per_split=16),indent=2)+'\n')
 print('Prepared four corpora, 16 maps each',flush=True)
if __name__=='__main__':main()
