"""Longer, asymmetric approaches to one-neighbor shelter; no evaluation replay."""
import hashlib,importlib.util,json,pathlib
from scenarios import ROOT,transform,specifications

ASSETS=ROOT/'learning-runs/autoregressive-survival-targeted-assets'

def target_rows(split):
    # Eight base geometries per split, each in all eight D4 orientations.
    settings=([(3,4,4,3),(4,3,5,3),(4,6,4,3),(6,4,5,4),
               (5,6,4,4),(6,5,5,3),(3,5,4,5),(5,3,6,4)] if split=='train' else
              [(4,5,5,5),(5,4,6,4),(5,5,5,4),(6,6,6,4),
               (3,6,5,4),(6,3,6,5),(4,7,5,5),(7,4,6,4)])
    rows=[]
    for variant,(gx,gy,left,top) in enumerate(settings):
        floor={(x,y) for x in range(-left,gx) for y in range(-top,gy)}|{(gx,gy)}
        # An asymmetric clipped corner varies topology without obstructing retreat.
        floor.remove((-left,-top))
        enemies=[(-1,-2),(0,-2),(1,-2),(-1,-3),(0,-3),(1,-3)]
        for g in range(8):
            rotated={tuple(transform(p,g)) for p in floor}
            padded=rotated|{(x,y) for x in range(-32,-26) for y in range(-28,-22)}
            goal=transform((gx,gy),g)
            assert sum(max(abs(x-goal[0]),abs(y-goal[1]))==1 for x,y in rotated)==1
            rows.append(dict(family='diagonal_pocket',variant=variant,orientation=g,split='target_'+split,
                             floor=sorted(padded),player=[0,0],goal=goal,enemies=[transform(p,g) for p in enemies],
                             layout_hash=hashlib.sha256(json.dumps(sorted(rotated)).encode()).hexdigest()))
    return rows

def prepare():
    original=specifications('train');old_eval=specifications('heldout')
    train=target_rows('train');heldout=target_rows('heldout')
    sets=[{s['layout_hash'] for s in rows} for rows in [original,old_eval,train,heldout]]
    for i,a in enumerate(sets):
        for b in sets[i+1:]:assert not a&b,'Cross-split geometry leakage'
    assert len(sets[2])==len(sets[3])==64
    spec=importlib.util.spec_from_file_location('compiler',ROOT/'branches/vision15-choice-practice-v1/scripts/map_compile.py')
    compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)
    ASSETS.mkdir(parents=True,exist_ok=True)
    for split,rows in [('train',original+train),('heldout',heldout)]:
        folder=ASSETS/split;folder.mkdir(exist_ok=True)
        for i,row in enumerate(rows):
            path=folder/f'map-{i:03d}.bin'
            if not path.exists():compiler.compile_map(row,path,i)
        (folder/'scenarios.json').write_text(json.dumps(rows,indent=2)+'\n')
        print('Prepared',split,len(rows),flush=True)

if __name__=='__main__':prepare()
