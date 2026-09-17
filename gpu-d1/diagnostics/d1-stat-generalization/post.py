"""Wait for the main experiment, then run nominal retention and tactical probes."""
import fcntl
import importlib.util
import json
import subprocess
import time
import torch
import runtime as r

def main():
    lock=(r.SUITE/'.post.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    start=time.monotonic()
    while not (r.SUITE/'result.json').exists():
        status=json.loads((r.SUITE/'status.json').read_text())
        if status.get('phase') in ['failed','stopped']:raise RuntimeError(status)
        if time.monotonic()-start>7200:raise TimeoutError('Main run did not complete within two hours')
        time.sleep(10)
    torch.set_num_threads(1)
    spec=importlib.util.spec_from_file_location('stat_runner',r.HERE/'run.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    selection=json.loads((r.SUITE/'selection.json').read_text());store=r.Store(r.SUITE,4*1024**3,10*1024**3)
    paths={'source':r.SOURCE,**{arm:r.SUITE/f'{arm}/checkpoints/{step}.pt' if step else r.SOURCE for arm,step in selection.items()}}
    # Declared before main-test results: larger nominal cohort to detect retention loss.
    for name,path in paths.items():
        model=r.load_model(path)
        for mode in ['sampled','greedy']:
            file=f'eval/{name}-nominal-test-{mode}.json'
            if not (r.SUITE/file).exists():
                result=runner.evaluate(model,[0],'test',100,64,mode,992301);store.json(file,result)
                print('nominal',name,mode,runner.brief(result),flush=True)
        del model;torch.cuda.empty_cache()
    subprocess.run([str(r.ROOT/'.venv/bin/python'),'-u',str(r.HERE/'probes.py')],check=True)
    subprocess.run([str(r.ROOT/'.venv/bin/python'),str(r.HERE/'summarize.py')],check=True)
    store.json('post-complete.json',dict(seconds_including_queue=time.monotonic()-start))
    print('post_complete',flush=True)

if __name__=='__main__':main()
