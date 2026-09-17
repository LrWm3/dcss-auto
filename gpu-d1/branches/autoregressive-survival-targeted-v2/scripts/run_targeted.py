"""Matched 5M continuations: existing practice versus half new approach practice."""
import fcntl,json,pathlib,subprocess,sys,time
import torch
import run_ring_ablations as runner
from tactical_models import Policy
from survival_eval import evaluate_tactics
from scenarios import ROOT,HERE
from target_scenarios import ASSETS

SOURCE=ROOT/'learning-runs/autoregressive-survival'
SUITE=ROOT/'learning-runs/autoregressive-survival-targeted'

def main():
    torch.set_num_threads(1);SUITE.mkdir(parents=True,exist_ok=True)
    store=runner.Store(SUITE,4*runner.GIB,10*runner.GIB)
    with (SUITE/'.pipeline.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);start=time.monotonic()
        try:
            cp=SOURCE/'runs/exploration-seed0/latest.pt'
            saved=torch.load(cp,map_location='cpu',weights_only=False)
            base=saved['decisions'];assert base==35000320
            steps=[base+((x+511)//512)*512 for x in [1000000,5000000]]
            template=dict(saved['job'],steps=steps[-1],evaluation_steps=steps,source_train_seconds=saved['train_seconds'],target_eval_corpus=str(ASSETS/'heldout'))
            manifest=dict(format='survival-targeted-v2',corpus=json.loads((SOURCE/'manifest.json').read_text())['corpus'],source_checkpoint=str(cp),source_sha256=runner.digest(cp),source_decisions=base,jobs=[],sources={str(p):runner.digest(p) for folder in ['scripts','src'] for p in (HERE/folder).glob('*') if p.is_file()},assets={str(p):runner.digest(p) for p in ASSETS.rglob('*') if p.is_file()},reset='Both arms reset tactical worlds and practice counters; retain ordinary states, policy, optimizer, and training RNG.')
            for arm in ['control','targeted']:
                job=dict(template,id=arm+'-seed0',name=arm,tactical_map_limit=64 if arm=='control' else 128)
                if arm=='targeted':job['tactical_corpus']=str(ASSETS/'train')
                manifest['jobs'].append(job)
                dest=pathlib.Path('runs')/job['id']/'latest.pt'
                if not (SUITE/dest).exists():
                    continuation=dict(saved,job=job,history=[],best=None,best_score=(-1.,-1.))
                    curriculum=continuation.pop('curriculum_state')
                    continuation['env_obs']=curriculum['raw_obs'];continuation['env_mask']=curriculum['raw_mask']
                    store.atomic(dest,lambda f:torch.save(continuation,f),256*runner.MIB)
            if (SUITE/'manifest.json').exists():assert json.loads((SUITE/'manifest.json').read_text())==manifest,'Source/configuration drift'
            else:store.json('manifest.json',manifest)
            baseline_file=ROOT/'results/autoregressive-survival-targeted-initial.json'
            if not baseline_file.exists():
                model=Policy('d4_exact',128).cuda().eval();model.load_state_dict(saved['model'])
                j=dict(template,tactical_eval_corpus=template['target_eval_corpus'])
                baseline=dict(source_checkpoint=str(cp),source_sha256=manifest['source_sha256'],policy=evaluate_tactics(model,j),controls=evaluate_tactics(model,j,controls=True))
                baseline_file.write_text(json.dumps(baseline,indent=2)+'\n');del model
                print('Initial novel-layout evaluation',baseline['policy']['greedy']['overall'],flush=True)
            del saved
            results={}
            for i,job in enumerate(manifest['jobs']):
                folder=SUITE/'runs'/job['id']
                store.json('status.json',dict(status='training',job=job['id'],queued=[x['id'] for x in manifest['jobs'][i+1:]]))
                print('Starting',job['id'],'additional decisions',steps[-1]-base,flush=True)
                if not (folder/'result.json').exists():subprocess.run([sys.executable,str(HERE/'scripts/run_ring_ablations.py'),'--worker',job['id'],'--output',str(SUITE),'--max-disk-gb','4','--min-free-gb','10'],check=True)
                final=json.loads((folder/'result.json').read_text());curve=json.loads((folder/'curve.json').read_text())
                assert final['decisions']==steps[-1] and [r['decisions'] for r in curve]==steps
                count=final['curriculum_counts'];assert count[0]+count[1]==steps[-1]-base and count[1]/sum(count[:2])==51/512
                results[job['id']]=dict(additional_train_seconds=final['additional_train_seconds'],curriculum_counts=count,evaluations=curve)
                (ROOT/'results/autoregressive-survival-targeted.json').write_text(json.dumps(dict(source_decisions=base,results=results,wall_seconds=time.monotonic()-start),indent=2)+'\n')
            store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start));print('Targeted comparison complete',flush=True)
        except Exception as exc:
            store.json('status.json',dict(status='failed',failure=f'{type(exc).__name__}: {exc}'));raise

if __name__=='__main__':main()
