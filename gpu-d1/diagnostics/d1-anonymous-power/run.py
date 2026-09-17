"""First seed-0 calibrated continuation; reuse the audited PPO update unchanged."""
import fcntl
import importlib.util
import json
import signal
import time
import traceback
import torch
import runtime as r

spec=importlib.util.spec_from_file_location('stat_runner',r.PRIOR/'run.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
runner.r=r
runner.ENDPOINTS=[500224,1000448,3000320,5000192]

def validation(model,store,arm,decisions):
    result={}
    for mode in ['sampled','greedy']:
        file=f'{arm}/validation-{decisions}-{mode}.json';path=r.SUITE/file
        if path.exists():value=json.loads(path.read_text())
        else:
            value=runner.evaluate(model,r.distribution()['panels']['validation'],mode=mode)
            store.json(file,value)
        result[mode]=value
        runner.log(store,phase='validation',arm=arm,decisions=decisions,mode=mode,**runner.brief(value))
    return result

runner.validation=validation

def main():
    torch.set_num_threads(1);started=time.monotonic();lock=(r.SUITE/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    store=r.Store(r.SUITE,4*1024**3,10*1024**3)
    def stop(*args):runner.STOP=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    pre=json.loads((r.SUITE/'preflight.json').read_text());assert all(r.digest(p)==v for p,v in pre['files'].items()),'Preflight source drift'
    manifest=dict(schema=1,seed=0,source=str(r.SOURCE),source_sha256=r.digest(r.SOURCE),distribution=r.distribution(),
        endpoints=runner.ENDPOINTS,training='Existing PPO settings, nominal replay anchors with identity removed; independent calibrated enemy stats; common speed10. No new practice resets, demonstrations, rewards, or heuristic overrides.',
        mechanics='24 enemies,2048 physical turns,three stairs,15x15 wall-blocking LOS and LOS-based wake,existing REST and navigation cues,+1 exit,-0.00001 per physical turn.',
        selection='Highest mean sampled/greedy validation exit rate; source eligible. Final checkpoint evaluated even if not selected.',
        files={str(p):r.digest(p) for p in [*r.HERE.glob('*.py'),r.HERE/'native.cu',r.HERE/'distribution.json',r.PRIOR/'run.py',r.PRIOR/'runtime.py',r.PRIOR/'learn.cu']})
    if (r.SUITE/'manifest.json').exists():assert json.loads((r.SUITE/'manifest.json').read_text())==manifest,'Manifest drift'
    else:store.json('manifest.json',manifest)
    try:
        baseline=validation(r.load_model(),store,'source',0)
        curve=runner.train('varied',store)
        if runner.STOP:runner.log(store,phase='stopped');return
        choices=[dict(decisions=0,**baseline),*curve]
        best=max(choices,key=lambda x:x['sampled']['exit_rate']+x['greedy']['exit_rate'])['decisions']
        store.json('selection.json',dict(decisions=best))
        endpoints=sorted({0,best,runner.ENDPOINTS[-1]})
        for step in endpoints:
            model=r.load_model(r.SOURCE if step==0 else r.SUITE/f'varied/checkpoints/{step}.pt')
            for panel in ['test_seen','test_unseen_enemies','ordinary','test_unseen_players']:
                for mode in ['sampled','greedy']:
                    file=f'eval/{step}-{panel}-{mode}.json'
                    if (r.SUITE/file).exists():continue
                    value=runner.evaluate(model,r.distribution()['panels'][panel],split='test',maps=100,repeats=8 if panel=='ordinary' else 2,mode=mode,seed=981011)
                    store.json(file,value);runner.log(store,phase='test_result',decisions=step,panel=panel,mode=mode,**runner.brief(value))
            del model;torch.cuda.empty_cache()
        store.json('result.json',dict(selection=best,endpoints=endpoints,wall_seconds=time.monotonic()-started))
        runner.log(store,phase='complete',selection=best,wall_seconds=time.monotonic()-started)
    except Exception as exc:
        runner.log(store,phase='failed',error=repr(exc),traceback=traceback.format_exc());raise

if __name__=='__main__':main()
