"""Old tactical fixtures evaluated with the current native autoregressive simulator.

No learning. Reuse old state constructors/geometry, adapt only action encoding.
Generated native sources and binaries live in ignored learning-runs storage.
"""
import argparse, ctypes as C, importlib.util, json, pathlib, subprocess, time
import numpy as np
import torch
import episode_credit as ec
from assets import FLAGS
from tactical_models import Policy
from learn_env_ring_multi import Env
ROOT = ec.ROOT
WORK = ROOT/'learning-runs/autoregressive-scenario-recheck'
NATIVE = ROOT/'branches/autoregressive-turn-cost-v1/src/learn.cu'
RESULT = ROOT/'results/autoregressive-scenario-recheck.json'
REPS = 64


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def compile_probe(name, source, extra=()):
    folder = WORK/name; folder.mkdir(parents=True, exist_ok=True)
    text = source.read_text()
    old = '#include "../../branches/vision15-clumps-v1/src/learn.cu"'
    assert old in text
    text = text.replace(old, '#include "'+str(NATIVE)+'"')
    text = text.replace('/512', f'/{REPS}').replace('%512', f'%{REPS}')
    if 'hall_control' in text:
        assert 'actions[i]=best<0?8:best;' in text
        text = text.replace('actions[i]=best<0?8:best;', 'actions[i]=best<0?16:8+best;')
        text = text.replace('q=a<8?neighbor(v.player,a):-1', 'q=(a>=8 && a<16)?neighbor(v.player,a-8):-1')
        text = text.replace('out[i*4+3]=a==8;', 'out[i*4+3]=a==16;')
    cu = folder/'probe.cu'; lib = folder/'probe.so'
    cu.write_text(text)
    subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12',
                    '-shared','-Xcompiler','-fPIC',*FLAGS,'-DCLUMP_MODE=0',*extra,str(cu),'-o',str(lib)], check=True)
    return lib


def policies():
    paths = {'imitation':ROOT/'learning-runs/autoregressive-imitation/imitation.pt',
             '10m':ROOT/'learning-runs/autoregressive-anchor-navigation/runs/navigation1-seed0/snapshots/000010000384.pt',
             '30m':ROOT/'learning-runs/autoregressive-anchor-navigation-30m/runs/navigation1-seed0/snapshots/000030000128.pt'}
    models = {}
    for name, path in paths.items():
        model = Policy('d4_exact',128).cuda().eval()
        model.load_state_dict(torch.load(path,map_location='cpu',weights_only=False)['model'])
        models[name] = model
    return paths, models


@torch.no_grad()
def retreat(name, models, geometry, distance=0, mirror=0):
    if geometry in ['hallway','hallway-six']:
        folder = ROOT/'diagnostics'/geometry
        maps = folder/'build'
        if not (maps/'map-0.bin').exists():
            maps.mkdir(parents=True,exist_ok=True)
            module('old_'+geometry,folder/'run.py').maps(maps)
        source = folder/'probe.cu'; flags=[]
        length = 1 if geometry=='hallway' else 3
    else:
        folder = ROOT/'diagnostics/pocket-symmetry'; maps=folder/'build'/f'{distance}-{mirror}'
        if not (maps/'map-0.bin').exists():
            maps.mkdir(parents=True,exist_ok=True)
            module('old_sym',folder/'run.py').maps(maps,distance,mirror)
        source=folder/'probe.cu';flags=[f'-DPOCKET_DISTANCE={distance}',f'-DPOCKET_MIRROR={mirror}'];length=distance
    lib=compile_probe(name,source,flags)
    env=Env(24*REPS,24,corpus=maps,map_limit=4,library_path=lib)
    p,i=C.c_void_p,C.c_int
    env.lib.hall_init.argtypes=[p,i,p,p,C.c_uint64,p,p,p]
    env.lib.hall_control.argtypes=[p,i,p,p,i,p]
    env.lib.hall_status.argtypes=[p,i,p,p,p]
    status=torch.empty((env.batch,4),device='cuda',dtype=torch.int32)
    rotations=torch.arange(env.batch,device='cuda')//REPS%4
    back=(2+rotations)%4 if geometry!='pocket' else 4+(1+mirror+rotations)%4
    rows=[dict(kind='weak' if g<12 else 'tough',hp=[6,12,18][g//4%3],rotation=g%4,mirror=mirror) for g in range(24)]
    output={'conditions':rows,'arms':{},'reps':REPS,'decision_cap':256,'maps':{str(p):ec.digest(p) for p in maps.glob('*.bin')},'source_sha256':ec.digest(source),'generated_sha256':ec.digest(WORK/name/'probe.cu')}
    arms=[('hold','scripted',False),('retreat','scripted',False)]
    arms += [(model,mode,False) for model in models for mode in ['sampled','greedy']]
    arms += [(model,'greedy',True) for model in ['imitation','30m']]
    for model_name,mode,force in arms:
        env.check(env.lib.hall_init(env.state.data_ptr(),env.batch,C.byref(env.config),C.byref(env.tables),900000,env.obs.data_ptr(),env.mask.data_ptr(),env.stream))
        assert env.obs.shape[1]==999 and env.mask.shape[1]==18
        assert (env.mask.gather(1,back[:,None])==1).all()
        assert (env.obs[:,959:999]<0).sum(1).eq(3 if geometry=='hallway' else 6).all()
        active=torch.ones(env.batch,device='cuda',dtype=torch.bool)
        won=active.clone().fill_(False);dead=won.clone();reached=won.clone()
        contact=torch.zeros(env.batch,device='cuda');wait=contact.clone();attack=contact.clone();turns=contact.clone()
        first=None;torch.manual_seed(900000)
        for step in range(256):
            if mode=='scripted':
                env.check(env.lib.hall_control(env.state.data_ptr(),env.batch,C.byref(env.config),env.actions.data_ptr(),int(model_name=='retreat'),env.stream));a=env.actions
            else:
                dist,_=models[model_name](env.obs,env.mask)
                a=dist.greedy() if mode=='greedy' else dist.sample()
                if step==0:
                    first=dict(retreat_probability=dist.probs.gather(1,back[:,None]).reshape(24,REPS).mean(1).tolist(),greedy_retreat=(dist.greedy()==back).float().reshape(24,REPS).mean(1).tolist())
                if force and step<length:a=back
            assert ((env.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all(), (name,model_name,step)
            env.check(env.lib.hall_status(env.state.data_ptr(),env.batch,a.data_ptr(),status.data_ptr(),env.stream))
            here=active&(status[:,0]>0);reached|=here;touch=here&(status[:,2]>0)
            contact+=touch;wait+=touch&(a==16);attack+=touch&(a>=8)&(a<16)
            env.step(a,active=active);turns+=active*env.out[:,26]
            won|=active&(env.out[:,2]>0);dead|=active&(env.out[:,6]>0);active&=env.out[:,1]==0
            if not active.any():break
        def means(x):return x.float().reshape(24,REPS).mean(1).tolist()
        key=model_name+'-'+mode+('-forced-route' if force else '')
        output['arms'][key]=dict(first=first,clear=means(won),death=means(dead),unresolved=means(active),turns=means(turns),reached_pocket=means(reached),protected_contact=means(contact),protected_wait=means(wait),protected_attack=means(attack))
        print(name,key,'clear',round(won.float().mean().item(),4),'reached',round(reached.float().mean().item(),4),flush=True)
    return output


@torch.no_grad()
def static(models):
    output=[]
    for mirror in [0,1]:
        maps=ROOT/'diagnostics/pocket-action/build'/str(mirror)
        if not (maps/'map-0.bin').exists():
            maps.mkdir(parents=True,exist_ok=True)
            module('old_sym',ROOT/'diagnostics/pocket-symmetry/run.py').maps(maps,6,mirror,center_pocket=True)
        lib=compile_probe('static'+str(mirror),ROOT/'diagnostics/pocket-action/probe.cu',['-DPOCKET_DISTANCE=6',f'-DPOCKET_MIRROR={mirror}'])
        env=Env(216,24,corpus=maps,map_limit=4,library_path=lib)
        p,i=C.c_void_p,C.c_int;env.lib.pocket_init.argtypes=[p,i,p,p,p,p,p]
        env.check(env.lib.pocket_init(env.state.data_ptr(),env.batch,C.byref(env.config),C.byref(env.tables),env.obs.data_ptr(),env.mask.data_ptr(),env.stream))
        assert (env.mask.sum(1)==2).all() and (env.mask[:,8:16].sum(1)==1).all()
        assert (env.obs[:,718:733]==0).all()
        predictions={name:model(env.obs,env.mask)[0].probs.cpu().numpy() for name,model in models.items()}
        for j in range(216):
            g=j//4
            output.append(dict(mirror=mirror,rotation=j%4,kind=g//9,hp=[6,12,18][g//3%3],enemy_hp=['full','half','one'][g%3],wait={name:float(probs[j,16]) for name,probs in predictions.items()}))
    # Corresponding native rotations/reflections must give identical WAIT mass.
    for name in models:
        a=np.array([row['wait'][name] for row in output]).reshape(2,54,4)
        assert np.max(a.max((0,2))-a.min((0,2)))<2e-6
    return output


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--only',default='all');args=ap.parse_args()
    torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
    WORK.mkdir(parents=True,exist_ok=True);paths,models=policies();start=time.monotonic()
    report=dict(training_performed=False,checkpoints={name:dict(path=str(path),sha256=ec.digest(path)) for name,path in paths.items()},native_sha256=ec.digest(NATIVE),flags=FLAGS,retreat={})
    def save():
        report['wall_seconds']=time.monotonic()-start
        RESULT.write_text(json.dumps(report,indent=2)+'\n')
    report['static']=static(models);save();print('Static symmetry check passed',flush=True)
    for name,geometry,distance,mirror in [('hallway','hallway',0,0),('hallway-six','hallway-six',0,0)]+[(f'pocket-{d}-mirror{m}','pocket',d,m) for d in [2,4,6] for m in ([0,1] if d==6 else [0])]:
        if args.only not in ['all',name]:continue
        report['retreat'][name]=retreat(name,models,geometry,distance,mirror);save()
    print('Tactical probes complete',flush=True)

if __name__=='__main__':main()
