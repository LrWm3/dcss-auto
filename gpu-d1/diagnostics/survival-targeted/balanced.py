"""Adaptive follow-up: farther genuine shelter and retention of two-sided retreats."""
import hashlib,importlib.util,json,pathlib,subprocess,sys,time,fcntl
import torch
ROOT=pathlib.Path(__file__).resolve().parents[2]
SCRIPTS=ROOT/'branches/autoregressive-survival-targeted-v2/scripts'
sys.path.insert(0,str(SCRIPTS))
import run_ring_ablations as runner
from scenarios import specifications,transform
from target_scenarios import target_rows
from survival_eval import evaluate_tactics
from tactical_models import Policy
ASSETS=ROOT/'learning-runs/autoregressive-survival-balanced-assets'
SUITE=ROOT/'learning-runs/autoregressive-survival-balanced'

def rows(split):
    result=[]
    parameters=([(4,4,2,3),(5,5,2,3),(6,6,2,3),(6,5,3,3),(5,6,2,4),(4,6,2,3),(6,4,2,3),(5,4,2,3)] if split=='train' else [(4,5,2,4),(5,5,2,4),(6,6,2,4),(6,5,2,4),(5,6,3,4),(4,6,3,4),(6,4,3,4),(7,5,2,4)])
    for variant,(gx,gy,left,top) in enumerate(parameters):
        floor={(x,y) for x in range(-left,gx) for y in range(-top,gy)}|{(gx,gy)}
        enemies=[(-1,-2),(0,-2),(1,-2),(-1,-3),(0,-3),(1,-3)]
        for g in range(8):
            f={tuple(transform(p,g)) for p in floor}
            result.append(dict(family='diagonal_pocket',variant=variant,orientation=g,split='far_'+split,floor=sorted(f|{(x,y) for x in range(-32,-26) for y in range(-28,-22)}),player=[0,0],goal=transform((gx,gy),g),enemies=[transform(p,g) for p in enemies],layout_hash=hashlib.sha256(json.dumps(sorted(f)).encode()).hexdigest()))
    return result

def groups():
    result=[]
    for variant in range(8):
        width=2+variant%3;bottom=1+variant//3;length=2+variant%2
        floor={(x,y) for x in range(-width,width+1) for y in range(-4,bottom+1)}
        floor-={(0,y) for y in range(-4,0)}
        floor|={(0,y) for y in range(bottom+1,bottom+length+1)}
        enemies=[(-width,-1),(-width,0),(-width,1),(width,-1),(width,0),(width,1)]
        for g in range(8):
            f={tuple(transform(p,g)) for p in floor}
            result.append(dict(family='separated_groups',variant=variant,orientation=g,split='retention_train',floor=sorted(f|{(x,y) for x in range(-32,-26) for y in range(-28,-22)}),player=[0,0],goal=transform((0,bottom+length),g),enemies=[transform(p,g) for p in enemies],layout_hash=hashlib.sha256(json.dumps(sorted(f)).encode()).hexdigest()))
    return result

def prepare():
    train=specifications('train')+target_rows('train')+rows('train')+groups()
    test=rows('heldout')
    train_hash={r['layout_hash'] for r in train}
    for heldout in [specifications('heldout'),target_rows('heldout'),test]:assert not train_hash&{r['layout_hash'] for r in heldout},'Split leakage'
    assert len({r['layout_hash'] for r in test})==64
    spec=importlib.util.spec_from_file_location('compiler',ROOT/'branches/vision15-choice-practice-v1/scripts/map_compile.py')
    compiler=importlib.util.module_from_spec(spec);spec.loader.exec_module(compiler)
    for split,data in [('train',train),('heldout',test)]:
        dest=ASSETS/split;dest.mkdir(parents=True,exist_ok=True)
        for i,row in enumerate(data):
            p=dest/f'map-{i:03d}.bin'
            if not p.exists():compiler.compile_map(row,p,i)
        (dest/'scenarios.json').write_text(json.dumps(data,indent=2)+'\n')
    print('Prepared 256 training maps and 64 further held-out layouts',flush=True)

def main():
    torch.set_num_threads(1);prepare();SUITE.mkdir(parents=True,exist_ok=True)
    with (SUITE/'.pipeline.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);start=time.monotonic()
        source=ROOT/'learning-runs/autoregressive-survival/runs/exploration-seed0/latest.pt'
        saved=torch.load(source,map_location='cpu',weights_only=False);assert saved['decisions']==35000320
        job=dict(saved['job'],id='balanced-seed0',name='balanced',steps=40000512,evaluation_steps=[36000768,40000512],source_train_seconds=saved['train_seconds'],tactical_corpus=str(ASSETS/'train'),tactical_map_limit=256,target_eval_corpus=str(ROOT/'learning-runs/autoregressive-survival-targeted-assets/heldout'))
        store=runner.Store(SUITE,4*runner.GIB,10*runner.GIB)
        manifest=dict(corpus=json.loads((ROOT/'learning-runs/autoregressive-survival/manifest.json').read_text())['corpus'],jobs=[job],source_checkpoint=str(source),source_sha256=runner.digest(source),sources={str(p):runner.digest(p) for p in [pathlib.Path(__file__),*SCRIPTS.glob('*.py')]},assets={str(p):runner.digest(p) for p in ASSETS.rglob('*') if p.is_file()})
        if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==manifest
        else:store.json('manifest.json',manifest)
        dest=pathlib.Path('runs')/job['id']/'latest.pt'
        if not (SUITE/dest).exists():
            c=dict(saved,job=job,history=[],best=None,best_score=(-1.,-1.));raw=c.pop('curriculum_state');c['env_obs']=raw['raw_obs'];c['env_mask']=raw['raw_mask']
            store.atomic(dest,lambda f:torch.save(c,f),256*runner.MIB)
        del saved
        store.json('status.json',dict(status='training',job=job['id']))
        try:
            if not (SUITE/'runs'/job['id']/'result.json').exists():subprocess.run([sys.executable,str(SCRIPTS/'run_ring_ablations.py'),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','4','--min-free-gb','10'],check=True)
            result=json.loads((SUITE/'runs'/job['id']/'result.json').read_text());assert result['decisions']==40000512
            curve=json.loads((SUITE/'runs'/job['id']/'curve.json').read_text())
            counts=result['curriculum_counts'];assert sum(counts[:2])==5000192
            (ROOT/'results/autoregressive-survival-balanced.json').write_text(json.dumps(dict(additional_train_seconds=result['additional_train_seconds'],curriculum_counts=counts,evaluations=curve,wall_seconds=time.monotonic()-start),indent=2,allow_nan=False)+'\n')
            store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Balanced follow-up complete',flush=True)
        except Exception as exc:
            store.json('status.json',dict(status='failed',failure=str(exc)));raise

if __name__=='__main__':main()
