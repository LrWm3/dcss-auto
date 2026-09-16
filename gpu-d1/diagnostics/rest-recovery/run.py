"""Post-training sleeping-enemy recovery probes; no policy updates."""
import argparse,ctypes as C,importlib.util,json,pathlib,subprocess,sys,time
import numpy as np
import torch
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
SLEEP_STATUS='--sleep-status' in sys.argv
EXPERIMENT='rest-sleep' if SLEEP_STATUS else 'rest-full'
PREFIX='rest-sleep-recovery' if SLEEP_STATUS else 'rest-recovery'
sys.path.insert(0,str(ROOT/f'branches/vision15-{EXPERIMENT}-v1/scripts'))
from assets import FLAGS
from learn_env_ring_multi import Env
from tactical_models import Policy

def prepare():
    work=ROOT/f'learning-runs/{PREFIX}-probe';work.mkdir(parents=True,exist_ok=True)
    maps=work/'maps';maps.mkdir(exist_ok=True)
    if not (maps/'map-0.bin').exists():
        spec=importlib.util.spec_from_file_location('map_compile',ROOT/'branches/vision15-choice-practice-v1/scripts/map_compile.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        mod.compile_map({'floor':[(x,y) for x in range(-10,11) for y in range(-10,11)]},maps/'map-0.bin',0)
    lib=work/'probe.so'
    subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*FLAGS,*(['-DPROBE_SLEEP'] if SLEEP_STATUS else []),'-DREST_ACTION=1','-DCLUMP_MODE=0',str(HERE/'probe.cu'),'-o',str(lib)],check=True)
    return work,maps,lib

def conditions():
    rows=[]
    for geometry,xy in [('off_axis_wake_plus_one',(7,1)),('straight_vision_edge',(7,0)),('outside_vision',(8,0))]:
        for hp in [2,9,18]:
            for difficulty,kind,enemy_hp in [('reference',3,28),('hard',4,48)]:
                for orientation in range(8):
                    x,y=xy
                    if orientation>=4:x=-x
                    for _ in range(orientation%4):x,y=-y,x
                    rows.append(dict(geometry=geometry,hp=hp,difficulty=difficulty,kind=kind,enemy_hp=enemy_hp,orientation=orientation,x=x,y=y))
    return rows

@torch.no_grad()
def evaluate(env,params,rows,reps,arm,mode):
    start=time.monotonic();n=env.batch;dev=env.device
    env.check(env.lib.probe_init(env.state.data_ptr(),n,C.byref(env.config),C.byref(env.tables),params.data_ptr(),reps,env.obs.data_ptr(),env.mask.data_ptr(),env.stream))
    stats=torch.zeros((n,5),device=dev);approach=torch.zeros(n,dtype=torch.int64,device=dev)
    def read():
        env.check(env.lib.probe_read(env.state.data_ptr(),n,C.byref(env.config),C.byref(env.tables),params.data_ptr(),stats.data_ptr(),approach.data_ptr(),env.stream))
    read()
    expected=torch.tensor([r['geometry']!='outside_vision' for r in rows],device=dev).repeat_interleave(reps)
    assert torch.equal(stats[:,2].bool(),expected), 'Unexpected LOS geometry'
    assert not stats[:,1].any()
    assert torch.equal(env.mask[:,9].bool(),(~expected)&(params[:,0]<18))
    assert (env.obs[~expected,225:650]==0).all(), 'Hidden monster leaked into observations'
    assert torch.all(env.obs[:,651]==0)
    if SLEEP_STATUS:
        assert torch.equal(env.obs[:,959:].sum(1),expected.float())
        assert (env.obs[:,959:]>=0).all()
    policy=None
    if arm in ['wait','rest']:
        checkpoint=ROOT/f'learning-runs/vision15-{EXPERIMENT}/runs/{arm}-seed0/snapshots/000010027008.pt'
        policy=Policy('d4_exact',128).to(dev).eval();policy.load_state_dict(torch.load(checkpoint,map_location=dev,weights_only=False)['model'])
    keys=['clear','death','timeout','decisions','turns','waits_asleep','waits_awake','rest_uses','rest_turns','rest_full','rest_interrupted','first_wait_probability','first_rest_probability','wake_hp','contact_hp','first_rest_hp','healed_before_wake','rest_before_wake']
    data={k:torch.zeros(n,device=dev) for k in keys}
    for k in ['wake_hp','contact_hp','first_rest_hp']:data[k].fill_(float('nan'))
    active=torch.ones(n,dtype=torch.bool,device=dev);healed=params[:,0]>=18
    woke=torch.zeros_like(active);contact=torch.zeros_like(active)
    torch.manual_seed(76031)
    for step in range(2048):
        idx=active.nonzero().flatten()
        if not len(idx):break
        if policy:
            masks=env.mask[idx].clone()
            if arm=='wait':masks[:,9]=0
            distribution,_=policy(env.obs[idx],masks)
            actions=torch.full((n,),8,dtype=torch.int64,device=dev)
            actions[idx]=distribution.probs.argmax(1) if mode=='greedy' else distribution.sample()
            if step==0:
                data['first_wait_probability'][idx]=distribution.probs[:,8]
                data['first_rest_probability'][idx]=distribution.probs[:,9]
        else:
            actions=approach.clone()
            if arm=='heal_first':actions[~healed]=8
            if step==0:data['first_wait_probability']=(actions==8).float()
        sleeping=stats[:,1]==0
        rest=(actions==9)&active
        data['first_rest_hp'][rest&data['first_rest_hp'].isnan()]=stats[rest&data['first_rest_hp'].isnan(),0]
        data['rest_before_wake']+= (rest&~woke).float()
        data['waits_asleep']+=((actions==8)&sleeping&active).float()
        data['waits_awake']+=((actions==8)&~sleeping&active).float()
        env.step(actions.contiguous(),active)
        out=env.out
        data['decisions']+=active.float()
        for key,col in [('turns',26),('rest_uses',34),('rest_turns',35),('rest_full',36),('rest_interrupted',37),('clear',2),('death',6),('timeout',7)]:data[key]+=out[:,col]*active
        assert not (out[active,38]>0).any(), 'Invalid rest selected'
        ended=active&(out[:,1]>0)
        read()
        # Native terminal transitions reset states; never record their post-reset state.
        live=active&~ended
        healed|=live&(stats[:,0]>=18)
        newwake=live&~woke&(stats[:,1]>0)
        data['wake_hp'][newwake]=stats[newwake,0]
        data['healed_before_wake'][newwake]=healed[newwake].float()
        woke|=newwake
        newcontact=live&~contact&(stats[:,3]<=1)
        data['contact_hp'][newcontact]=stats[newcontact,0];contact|=newcontact
        active&=~ended
        if step and step%512==0:print(arm,mode,'step',step,'active',int(active.sum()),flush=True)
    assert not active.any(), 'Evaluation did not finish at native decision deadline'
    arrays={k:v.cpu().numpy().reshape(len(rows),reps) for k,v in data.items()}
    results=[]
    for geometry in dict.fromkeys(r['geometry'] for r in rows):
        for hp in [2,9,18]:
            for difficulty in ['reference','hard']:
                indices=[i for i,r in enumerate(rows) if r['geometry']==geometry and r['hp']==hp and r['difficulty']==difficulty]
                item=dict(geometry=geometry,hp=hp,difficulty=difficulty,episodes=len(indices)*reps)
                for key,arr in arrays.items():
                    values=arr[indices].flatten();valid=np.isfinite(values)
                    item[key]=float(values[valid].mean()) if valid.any() else None
                    if key in ['wake_hp','contact_hp','first_rest_hp']:item[key+'_n']=int(valid.sum())
                item['ever_rested']=float((arrays['rest_uses'][indices]>0).mean())
                item['ever_waited_asleep']=float((arrays['waits_asleep'][indices]>0).mean())
                item['rested_before_wake']=float((arrays['rest_before_wake'][indices]>0).mean())
                results.append(item)
    print(arm,mode,'finished',round(time.monotonic()-start,1),'seconds',flush=True)
    return dict(arm=arm,mode=mode,seconds=time.monotonic()-start,conditions=results)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reps',type=int,default=128);parser.add_argument('--arms',nargs='+',default=['engage_now','heal_first','wait','rest']);parser.add_argument('--greedy',action='store_true');parser.add_argument('--sleep-status',action='store_true');args=parser.parse_args()
    torch.set_num_threads(1);torch.backends.cuda.matmul.allow_tf32=False
    work,maps,lib=prepare();rows=conditions();n=len(rows)*args.reps
    env=Env(batch=n,corpus=maps,library_path=lib)
    p,i=C.c_void_p,C.c_int
    env.lib.probe_init.argtypes=[p,i,p,p,p,i,p,p,p]
    env.lib.probe_read.argtypes=[p,i,p,p,p,p,p,p]
    params=torch.tensor([[r['hp'],r['kind'],r['enemy_hp'],r['x'],r['y']] for r in rows],dtype=torch.int32,device='cuda').repeat_interleave(args.reps,0).contiguous()
    for arm in args.arms:
        for mode in (['sampled','greedy'] if args.greedy and arm in ['wait','rest'] else ['sampled' if arm in ['wait','rest'] else 'scripted']):
            result=evaluate(env,params,rows,args.reps,arm,mode)
            result['design']=dict(sleep_status=SLEEP_STATUS,training_suite=f'vision15-{EXPERIMENT}',replicates_per_orientation=args.reps,orientations=8,decision_limit=2048,player_max_hp=18,room='21x21 open room; center start',checkpoint_decisions=10027008,rng_seed=930000,policy_seed=76031,conditions=rows)
            path=ROOT/f'results/{PREFIX}-{arm}-{mode}.json';path.write_text(json.dumps(result,indent=2)+'\n');print(path,flush=True)
if __name__=='__main__':main()
