"""Matched one-seed, 1M-decision pilot: ordinary continuation vs bypass resets."""
import fcntl
import importlib.util
import json
import signal
import time
import torch
import runtime as r

spec=importlib.util.spec_from_file_location('stat_runner',r.a.PRIOR/'run.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner);runner.r=r
runner.ENDPOINTS=[500224,1000448]
spec=importlib.util.spec_from_file_location('behavior_runner',r.a.HERE/'behavior.py')
behavior=importlib.util.module_from_spec(spec);spec.loader.exec_module(behavior)

@torch.no_grad()
def practice(model,split='validation'):
    bank=torch.load(r.SUITE/f'practice-{split}.pt',weights_only=False)
    e=r.Env(split,batch=2048,seed=4181,clump=0,balanced=True)
    results={}
    for mode in ['greedy','sampled']:
        raw=behavior.rollouts(e,bank,model,mode,repeats=8,seed=8131991)
        count=len(raw['rows'])*raw['repeats']
        results[mode]={'episodes':count,**{k:sum(x[k] for x in raw['rows'])/count for k in ['exits','deaths','timeouts','exit_without_kill']},'mean_waits':sum(x['wait_actions'] for x in raw['rows'])/len(raw['rows'])}
    return results

TRAIN_ENVS=[]
BaseEnv=r.Env
class TrackedEnv(BaseEnv):
    def __init__(self,*args,**kw):
        # Both named arms use the varied-stat training distribution.
        if 'varied' in kw:kw['varied']=True
        super().__init__(*args,**kw)
        if kw.get('varied'):TRAIN_ENVS.append(self)
r.Env=TrackedEnv

def validation(model,store,arm,decisions):
    result={}
    for mode in ['sampled','greedy']:
        value=runner.evaluate(model,list(range(9)),mode=mode)
        store.json(f'{arm}/validation-{decisions}-{mode}.json',value);result[mode]=value
        runner.log(store,phase='validation',arm=arm,decisions=decisions,mode=mode,**runner.brief(value))
    probe=practice(model);store.json(f'{arm}/practice-{decisions}.json',probe)
    runner.log(store,phase='practice',arm=arm,decisions=decisions,results=probe)
    if TRAIN_ENVS:store.json(f'{arm}/episode-counts-{decisions}.json',{'rows':['ordinary','practice'],'columns':['episodes','exits','deaths','timeouts'],'counts':TRAIN_ENVS[-1].completed.cpu().tolist()})
    return result
runner.validation=validation

def main():
    torch.set_num_threads(1);lock=(r.SUITE/'.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    store=r.Store(r.SUITE,4*1024**3,10*1024**3);started=time.monotonic()
    def stop(*args):runner.STOP=True
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    assert (r.SUITE/'preflight.json').exists()
    store.json('manifest.json',dict(source=str(r.SOURCE),source_sha256=r.digest(r.SOURCE),endpoints=runner.ENDPOINTS,seed=0,arms={'control':'ordinary varied-stat continuation','practice':'40% reset attempts, geometry acceptance determines actual fraction'},reward='+1 exit -0.00001 per physical turn',files={str(p):r.digest(p) for p in r.HERE.glob('*') if p.is_file()}))
    validation(r.load_model(),store,'source',0)
    for arm,mix in [('control',0),('practice',40)]:
        r.MIX=mix
        runner.train(arm,store)
        if runner.STOP:return
    # Fixed final endpoint: do not select checkpoints on test results.
    for arm in ['source','control','practice']:
        path=r.SOURCE if arm=='source' else r.SUITE/f'{arm}/checkpoints/{runner.ENDPOINTS[-1]}.pt'
        model=r.load_model(path)
        store.json(f'eval/{arm}-practice.json',practice(model,'test'))
        for panel in ['test_seen','test_unseen_enemies','ordinary']:
            for mode in ['sampled','greedy']:
                value=runner.evaluate(model,r.a.distribution()['panels'][panel],split='test',maps=100,repeats=8 if panel=='ordinary' else 2,mode=mode,seed=981011)
                store.json(f'eval/{arm}-{panel}-{mode}.json',value)
                runner.log(store,phase='test',arm=arm,panel=panel,mode=mode,**runner.brief(value))
    store.json('result.json',{'wall_seconds':time.monotonic()-started});runner.log(store,phase='complete',wall_seconds=time.monotonic()-started)

if __name__=='__main__':main()
