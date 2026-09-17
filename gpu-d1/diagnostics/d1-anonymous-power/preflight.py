import ctypes as C
import json
import time
import torch
import runtime as r

def main():
    torch.set_num_threads(1);started=time.monotonic();r.build();d=r.distribution();report={}
    cases=list(range(9))+[18]
    cpu=r.Env(assignments=cases,seed=441,device='cpu',map_limit=2,clump=0,balanced=True)
    gpu=r.Env(assignments=cases,seed=441,map_limit=2,clump=0,balanced=True)
    for tick in range(128):
        assert torch.equal(cpu.obs,gpu.obs.cpu()),tick
        assert torch.equal(cpu.mask,gpu.mask.cpu()),tick
        a=cpu.heuristic().clone();cpu.step(a);gpu.step(a.cuda())
        assert torch.equal(cpu.out,gpu.out.cpu()),tick
    report['cpu_cuda_decisions']=128*len(cases)
    for case in cases:
        e=r.Env(assignments=[case],device='cpu',seed=811,map_limit=2,clump=0)
        assert e.lib.stats_semantics(C.byref(e.config),C.byref(e.tables))==0
    report['hidden_enemy_rest_deadline_stairs_profiles']=len(cases)
    e=r.Env(batch=2048,varied=True,seed=1101,clump=0,map_limit=2)
    head=e.state[:,:340].contiguous().view(torch.int32).cpu();meta=e.metadata_tensor().cpu()
    assert torch.equal(head[:,3],meta[:,3].int()) and torch.equal(head[:,4],meta[:,4].int())
    assert not e.obs[:,450:650].reshape(-1,40,5)[:,:,3].any()
    assert not head[:,29:45].any() and not head[:,69:85].any()
    counts=[]
    for template in d['train_templates']:
        match=(head[:,5:29]==template['hp'])&(head[:,45:69]==template['damage_cap'])
        counts.append(int(match.sum()))
    assert sum(counts)==2048*24
    assert all(.14<x/(2048*24)<.19 for x in counts)
    profile_counts=torch.bincount(meta[:,0],minlength=9).tolist();assert all(x>100 for x in profile_counts)
    report['enemy_template_counts']=counts;report['profile_counts']=profile_counts
    # Confirm selected risks using independent futures, after catalogue selection.
    vectors=[(hp,pd,t['hp'],t['damage_cap'],percent) for hp,pd in d['player_order'] for t in d['train_templates'] for percent in [50,100]]
    v=torch.tensor(vectors,dtype=torch.int32,device='cuda');out=torch.empty(len(vectors)*8192,5,device='cuda')
    e.check(e.lib.power_duels(C.byref(e.config),v.data_ptr(),len(vectors),8192,97801101,out.data_ptr(),e.stream))
    z=out.cpu().reshape(len(vectors),8192,5);assert not z[:,:,4].any()
    confirmation=[dict(player_hp=x[0],player_damage=x[1],enemy_hp=x[2],enemy_damage=x[3],hp_percent=x[4],trials=8192,deaths=int((a[:,0]==0).sum()),death_rate=float((a[:,0]==0).float().mean()),turns=float(a[:,1].mean())) for x,a in zip(vectors,z)]
    (r.ROOT/'results/d1-anonymous-power-confirmation.json').write_text(json.dumps(confirmation,indent=2)+'\n')
    report['confirmation']=confirmation
    full={tuple(x[k] for k in ['player_hp','player_damage','enemy_hp','enemy_damage']):x['death_rate'] for x in confirmation if x['hp_percent']==100}
    for t in d['train_templates']:
        if t['category']=='weak':assert max(full[hp,pd,t['hp'],t['damage_cap']] for hp,pd in d['player_order'])<.01
        if t['category']=='crossover':assert full[10,2,t['hp'],t['damage_cap']]>.30 and full[30,6,t['hp'],t['damage_cap']]<.02
        if t['category']=='dangerous':assert min(full[hp,pd,t['hp'],t['damage_cap']] for hp,pd in d['player_order'])>.30
    report['files']={str(p):r.digest(p) for p in [r.HERE/'native.cu',r.HERE/'runtime.py',r.HERE/'distribution.json',r.PRIOR/'learn.cu']}
    report['seconds']=time.monotonic()-started
    (r.SUITE/'preflight.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS',report['cpu_cuda_decisions'],'CPU/CUDA decisions; semantics; anonymous fields; independent stat sampling; fresh-risk confirmation',report['seconds'],flush=True)

if __name__=='__main__':main()
