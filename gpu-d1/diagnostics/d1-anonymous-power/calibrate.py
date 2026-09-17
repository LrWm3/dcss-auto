"""No policy training: measure fight risks and select a common enemy catalogue."""
import ctypes as C
import itertools
import json
import time
import torch
import runtime as r

NOMINAL=[18,4,24,8,10,12,16,12,10,3,3,1,5,5,3]

def main():
    torch.set_num_threads(1);start=time.monotonic();r.build()
    cpu=r.Env(batch=1,device='cpu',vectors=[NOMINAL],map_limit=8,clump=0)
    matched=cpu.lib.power_duel_check(C.byref(cpu.config),C.byref(cpu.tables));assert matched==512
    e=r.Env(batch=1,vectors=[NOMINAL],map_limit=2,clump=0)
    cases=list(itertools.product([10,12,18,24,30],[2,3,4,5,6],[6,10,16,24,36,52,72],[2,4,6,8,10,12,16,20],[50,100]))
    rows=[];reps=2048
    for start_idx in range(0,len(cases),128):
        vectors=torch.tensor(cases[start_idx:start_idx+128],dtype=torch.int32,device='cuda');out=torch.empty(len(vectors)*reps,5,device='cuda');seed=95110001+start_idx*reps
        e.check(e.lib.power_duels(C.byref(e.config),vectors.data_ptr(),len(vectors),reps,seed,out.data_ptr(),e.stream))
        samples=out.cpu().reshape(len(vectors),reps,5)
        assert not samples[:,:,4].any()
        if start_idx==0:
            p=C.c_void_p;i=C.c_int;cpu.lib.power_cpu_duels.argtypes=[p,p,i,i,C.c_uint64,p]
            host=vectors[:4].cpu().contiguous();expected=torch.empty(4*reps,5)
            assert cpu.lib.power_cpu_duels(C.byref(cpu.config),host.data_ptr(),4,reps,seed,expected.data_ptr())==0
            assert torch.equal(expected.reshape(4,reps,5),samples[:4])
        for vector,values in zip(cases[start_idx:start_idx+128],samples):
            hp,damage,eh,ed,percent=vector;alive=values[:,0].bool()
            rows.append(dict(player_hp=hp,player_damage=damage,enemy_hp=eh,enemy_damage=ed,hp_percent=percent,deaths=int((~alive).sum()),trials=reps,death_rate=float((~alive).float().mean()),turns=float(values[:,1].mean()),survivor_hp=float(values[alive,2].mean()) if alive.any() else None,damage=float(values[:,3].mean())))
    report=dict(schema=1,rows=rows,checks=dict(full_simulator_matched_duels=matched,cpu_cuda_matched_duels=4*reps),seconds=time.monotonic()-start,
        design='Adjacent awake enemy, common speed10, full/half player HP, attack every turn. Actual production attack/defense/regen rules. Independent seeded futures for every case. These are conditional combat risks, not floor death predictions.')
    (r.SUITE/'calibration.json').write_text(json.dumps(report))
    (r.ROOT/'results/d1-anonymous-power-calibration.json').write_text(json.dumps(report,indent=2)+'\n')
    print('calibration_complete',report['seconds'],'seconds',flush=True)
    choose(report)

def choose(report):
    players=list(itertools.product([10,18,30],[2,4,6]));templates=list(itertools.product([6,10,16,24,36,52,72],[2,4,6,8,10,12,16,20]))
    risks={(x['player_hp'],x['player_damage'],x['enemy_hp'],x['enemy_damage']):x['death_rate'] for x in report['rows'] if x['hp_percent']==100}
    def profile(t):return [risks[(*p,*t)] for p in players]
    weak=[t for t in templates if max(profile(t))<=.01]
    dangerous=[t for t in templates if min(profile(t))>=.30]
    crossover=[t for t in templates if risks[(10,2,*t)]>=.30 and risks[(30,6,*t)]<=.02]
    assert len(weak)>=4 and len(dangerous)>=2 and len(crossover)>=6,(weak,dangerous,crossover)
    # Pick relatively substantial harmless enemies, diverse crossover profiles,
    # and a dangerous anchor near 50% death risk for the strongest player.
    weak.sort(key=lambda t:((t[0]-10)**2/16+(t[1]-4)**2,t))
    dangerous.sort(key=lambda t:(abs(risks[(30,6,*t)]-.5),t))
    crossover.sort(key=lambda t:(risks[(18,4,*t)],t))
    selected_cross=[]
    for target in [.03,.12,.25]:
        chosen=min([t for t in crossover if t not in selected_cross and t[1] not in [v[1] for v in selected_cross]],key=lambda t:abs(risks[(18,4,*t)]-target))
        selected_cross.append(chosen)
    train=[weak[0],weak[1],*selected_cross,dangerous[0]]
    held=[]
    for t in train:
        category=weak if t in weak else dangerous if t in dangerous else crossover
        q=min([v for v in category if v not in train and v not in held],key=lambda v:sum((a-b)**2 for a,b in zip(profile(v),profile(t))))
        held.append(q)
    vectors=[];profiles=[]
    def add(name,p,ts):
        profiles.append(dict(id=len(vectors),name=name,player_hp=p[0],player_damage=p[1],enemy_templates=ts))
        vectors.append([*p,24,*[t[0] for t in ts],*[t[1] for t in ts]])
    for p in players:add('training_mix',p,train)
    for p in players:add('unseen_enemy_mix',p,held)
    add('ordinary_anonymous',(18,4),[(8,3),(10,3),(12,1),(16,5),(12,5),(10,3)])
    for p in [(14,2),(14,4),(14,6),(24,2),(24,4),(24,6)]:add('unseen_player_hp',p,train)
    result=dict(schema=1,selection='Measured full-health fight risks. Broader player grid chosen because the old12/18/24HP and3/4/5damage grid had only three crossover candidates, insufficient for separate training and held-out catalogues. Oracle selection does not use learned-policy outcomes.',
        seed=0,training_profiles=9,player_levels=dict(hp=[10,18,30],damage_cap=[2,4,6]),
        train_templates=[dict(hp=t[0],damage_cap=t[1],category='weak' if i<2 else 'crossover' if i<5 else 'dangerous',risk_by_player=profile(t)) for i,t in enumerate(train)],
        heldout_templates=[dict(hp=t[0],damage_cap=t[1],risk_by_player=profile(t)) for t in held],
        mixture='Uniform over 9 player stat pairs per episode; independently uniform over 6 enemy templates per enemy: 1/3 weak, 1/2 crossover, 1/6 dangerous. Same enemy pool at every player strength.',
        player_order=players,vectors=vectors,profiles=profiles,
        panels=dict(validation=list(range(9))+[18],test_seen=list(range(9)),test_unseen_enemies=list(range(9,18)),ordinary=[18],test_unseen_players=list(range(19,25))))
    (r.HERE/'distribution.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['train_templates'],indent=2),flush=True)

if __name__=='__main__':main()
