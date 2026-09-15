"""Compare uninterrupted PPO against checkpoint/resume, including live worlds."""
import pathlib
import subprocess
import sys
import tempfile
import torch
from learn_env import ROOT


def main():
    with tempfile.TemporaryDirectory(prefix='resume-test-',dir=ROOT/'learning-runs') as tmp:
        base=pathlib.Path(tmp)
        common=[sys.executable,str(ROOT/'scripts/train_clear.py'),'--enemies','8',
                '--seeds','0','--batch','64','--horizon','8','--minibatch','512',
                '--eval-episodes','37']
        for name,steps,resume in [('full',1024,None),('half',512,None),('resumed',1024,base/'half')]:
            command=common+['--steps',str(steps),'--output',str(base/name)]
            if resume: command+=['--resume-from',str(resume)]
            result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            if result.returncode: raise RuntimeError(result.stdout)
        a=torch.load(base/'full/seed-0/policy-1024.pt',weights_only=False,map_location='cpu')
        b=torch.load(base/'resumed/seed-0/policy-1024.pt',weights_only=False,map_location='cpu')
        def equal(a,b,path):
            if isinstance(a,torch.Tensor): assert torch.equal(a,b),path
            elif isinstance(a,dict):
                assert a.keys()==b.keys(),path
                for k in a: equal(a[k],b[k],f'{path}.{k}')
            elif isinstance(a,list):
                assert len(a)==len(b),path
                for j,(x,y) in enumerate(zip(a,b)): equal(x,y,f'{path}.{j}')
            else: assert a==b,path
        for key in ('model','optimizer','env_state','env_obs','env_mask','torch_rng','cuda_rng','decisions'):
            equal(a[key],b[key],key)
        print('PASS uninterrupted vs resumed PPO: exact weights, optimizer, live worlds, observations, masks and RNGs')

if __name__=='__main__': main()
