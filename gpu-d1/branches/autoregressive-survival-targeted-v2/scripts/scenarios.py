"""Small survival encounter layouts; train/evaluation geometry is disjoint."""
import hashlib, importlib.util, json, pathlib, subprocess
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[3]
HERE=pathlib.Path(__file__).resolve().parents[1]
ASSETS=ROOT/'learning-runs/autoregressive-survival-assets'
FLAGS=['-DPROGRESS_INPUT=2','-DKILL_MILLI=0','-DCLEAR_MILLI=1000','-DDEATH_MILLI=0','-DFRONTIER_TRAVEL=0','-DOGRE_COUNT=0','-DMONSTER_WAKE_LOS=1','-DTERRAIN_LOS=1','-DGLOBAL_ENEMIES=0','-DLEARN_ENEMIES=40','-DMULTI_MAP','-DSLEEP_ON','-DEXPLORE_REWARD','-DMARK_WALLS','-DEXPLORE_MILLI=0','-DFRONTIER_RING_MEMORY_WALLS_OBS','-DKNOWN_FRONTIER','-DFRONTIER_ROUTE_CUE_OBS','-DFAST_FRONTIER','-DLEARN_BLOCK_SIZE=4','-DCLEAR_PER_ENEMY_MILLI=0','-DCLUMP_MODE=0']
FAMILIES=['hallway','diagonal_pocket','passing_enemy','separated_groups']


def transform(p,g):
    x,y=p
    if g>=4:x=-x
    for _ in range(g%4):x,y=-y,x
    return [x,y]


def specifications(split):
    rows=[]
    for family in FAMILIES:
        for variant in ([0,1] if split=='train' else [2,3]):
            width=2+variant%2
            enemies=[(-1,-1),(0,-1),(1,-1),(-1,-2),(0,-2),(1,-2)]
            if family=='hallway':
                length=[1,3,2,4][variant]
                floor={(x,y) for x in range(-width,width+1) for y in range(-3-(variant//2),0)}
                floor|={(0,y) for y in range(length+1)};goal=(0,length)
            elif family=='diagonal_pocket':
                d=variant+2
                floor={(x,y) for x in range(-3,d) for y in range(-3,d)}|{(d,d)};goal=(d,d)
                enemies=[(-1,-2),(0,-2),(1,-2),(-1,-3),(0,-3),(1,-3)]
            elif family=='passing_enemy':
                end=3+variant%2
                floor={(x,y) for x in range(-3-variant//2,3) for y in range(-3,2)}
                floor|={(x,1) for x in range(3,end+1)}|{(end+1,2)};goal=(end+1,2)
                enemies=[(1,1),(-1,-2),(0,-2),(1,-2),(-1,-3),(0,-3)]
            else:
                width=3+variant%2;bottom=2+variant//2
                floor={(x,y) for x in range(-width,width+1) for y in range(-3,bottom+1)}
                floor-={(0,y) for y in range(-3,0)}
                floor|={(0,y) for y in range(bottom+1,bottom+4)};goal=(0,bottom+3)
                enemies=[(-width,-1),(-width,0),(-width,1),(width,-1),(width,0),(width,1)]
            assert (0,0) in floor and goal in floor and all(p in floor for p in enemies)
            for g in range(8):
                rotated={tuple(transform(p,g)) for p in floor}
                # Disconnected padding supports the native terminal auto-reset.
                padded=rotated|{(x,y) for x in range(-32,-26) for y in range(-28,-22)}
                rows.append(dict(family=family,variant=variant,orientation=g,split=split,
                                 floor=sorted(padded),player=[0,0],goal=transform(goal,g),
                                 enemies=[transform(p,g) for p in enemies],
                                 layout_hash=hashlib.sha256(json.dumps(sorted(rotated)).encode()).hexdigest()))
    return rows


def prepare():
    ASSETS.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('compiler',ROOT/'branches/vision15-choice-practice-v1/scripts/map_compile.py')
    compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)
    splits={split:specifications(split) for split in ['train','heldout']}
    assert not {r['layout_hash'] for r in splits['train']} & {r['layout_hash'] for r in splits['heldout']}
    for split,rows in splits.items():
        folder=ASSETS/split;folder.mkdir(exist_ok=True)
        for i,row in enumerate(rows):
            path=folder/f'map-{i:03d}.bin'
            if not path.exists():compiler.compile_map(row,path,i)
        (folder/'scenarios.json').write_text(json.dumps(rows,indent=2)+'\n')
    lib=ASSETS/'survival.so'
    subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*FLAGS,str(HERE/'src/survival_probe.cu'),'-o',str(lib)],check=True)
    lib.with_suffix('.sha256').write_text(hashlib.sha256(lib.read_bytes()).hexdigest()+'\n')
    print('Prepared 64 training and 64 held-out layouts',flush=True)
    return lib

if __name__=='__main__':prepare()
