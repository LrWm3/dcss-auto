"""Protect the initial policy outside awake-enemy encounters, leaving combat free."""
import fcntl,json,pathlib,subprocess,sys,time
import torch
import episode_credit as ec
import run_ring_ablations as runner
import imitation_anchor
ROOT=ec.ROOT

def safe_kl(target,actual,obs):
    # Audited v1 schema: 959:999 are visible discovery slots; asleep=+1,
    # awake=-1, nonvisible/dead/unused=0. No hidden enemy information.
    safe=(obs[:,959:999]>=0).all(-1).float()
    kl=(target*(target.clamp_min(1e-30).log()-actual.clamp_min(1e-30).log())).sum(-1)
    return (safe*kl).sum()/safe.sum().clamp_min(1)

class NavigationAnchor(imitation_anchor.ImitationAnchor):
    def loss(self,model,obs,mask):
        n=min(self.size//2,len(obs));replay=torch.randint(len(self.obs),(n,),device=obs.device);current=torch.randint(len(obs),(n,),device=obs.device)
        x=torch.cat((obs[current],self.obs[replay]));m=torch.cat((mask[current],self.mask[replay]))
        with torch.no_grad():target=self.reference(x,m)[0].probs
        actual=model(x,m)[0].probs
        return self.weight*safe_kl(target,actual,x)

def selftest():
    obs=torch.zeros(3,999);obs[1,959]=-1;obs[2,960]=1
    target=torch.tensor([[.8,.2]]*3);actual=torch.tensor([[.4,.6]]*3,requires_grad=True)
    loss=safe_kl(target,actual,obs);loss.backward()
    assert loss>0 and actual.grad[0].abs().sum()>0 and actual.grad[1].abs().sum()==0 and actual.grad[2].abs().sum()>0
    obs[:,959]=-1;assert safe_kl(target,actual,obs)==0
    print('Awake/sleep/nonvisible gating and combat-gradient exclusion passed',flush=True)

def main():
    selftest()
    if '--worker' in sys.argv:
        imitation_anchor.ImitationAnchor=NavigationAnchor
        return runner.main()
    suite=ROOT/'learning-runs/autoregressive-anchor-navigation';suite.mkdir(parents=True,exist_ok=True);store=runner.Store(suite,3*runner.GIB,10*runner.GIB)
    with (suite/'.pipeline.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        old=json.loads((ROOT/'learning-runs/autoregressive-anchor-screen/manifest.json').read_text())
        job=dict(old['jobs'][0],id='navigation1-seed0',name='navigation1',anchor_kind='policy',anchor_weight=1.,anchor_scope='no_visible_awake_enemy')
        manifest=dict(corpus=old['corpus'],jobs=[job],sources={str(p):runner.digest(p) for p in [pathlib.Path(__file__),pathlib.Path(runner.__file__),pathlib.Path(imitation_anchor.__file__)]})
        if (suite/'manifest.json').exists():assert json.loads((suite/'manifest.json').read_text())==manifest
        else:store.json('manifest.json',manifest)
        start=time.monotonic();store.json('status.json',dict(status='training',job=job['id']));folder=suite/'runs'/job['id']
        if not (folder/'result.json').exists():subprocess.run([sys.executable,__file__,'--worker',job['id'],'--output',str(suite),'--max-disk-gb','3','--min-free-gb','10'],check=True)
        result={job['id']:dict(ppo=json.loads((folder/'result.json').read_text()),evaluations=json.loads((folder/'curve.json').read_text()))}
        (ROOT/'results/autoregressive-anchor-navigation.json').write_text(json.dumps(dict(results=result,wall_seconds=time.monotonic()-start),indent=2)+'\n')
        store.json('status.json',dict(status='complete',wall_seconds=time.monotonic()-start))
if __name__=='__main__':main()
