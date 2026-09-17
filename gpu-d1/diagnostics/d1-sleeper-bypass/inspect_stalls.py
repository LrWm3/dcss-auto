"""Inspect geometry and causal observation interventions on captured wait stalls."""
import json
import torch
import runtime as r

@torch.no_grad()
def main():
    torch.set_num_threads(1);r.build()
    b=torch.load(r.a.SUITE/'behavior/stalls.pt',weights_only=False);n=len(b['rows'])
    # Original world ids reach 1799; retain compatible assignment storage.
    e=r.Env('test',assignments=[p for p in range(9) for _ in range(200)],seed=981011,seed_period=200,map_limit=100,clump=0,balanced=True)
    for k in ['state','obs','mask']:getattr(e,k)[:n].copy_(b[k].cuda())
    raw=e.inspect()[:n];m=r.load_model();x=e.obs[:n].clone();mask=e.mask[:n].clone()
    variants={'original':x}
    absent=x.clone();absent[:,225:450]=0;absent[:,450:650]=0;absent[:,959:999]=0;absent[:,1018:]=0;variants['hide_enemy_observation']=absent
    weak=x.clone();visible=weak[:,450:650].reshape(n,40,5)[:,:,4]>0
    weak[:,1018:].reshape(n,40,2)[:,:,1][visible]=.2;variants['enemy_damage_cap_1']=weak
    awake=x.clone();awake[:,959:999][visible]=-1;variants['enemy_appears_awake']=awake
    unknown_sleep=x.clone();unknown_sleep[:,959:999]=0;variants['zero_sleep_status']=unknown_sleep
    strong=x.clone();strong[:,1015:1018]=torch.tensor([30/18,30/18,6/4],device='cuda');variants['player_30hp_damage6']=strong
    nofront=x.clone();nofront[:,FRONTIER:FRONTIER+15]=0;variants['zero_frontier']=nofront
    safe=x.clone()
    for i,z in enumerate(raw):
        d=int(z[10]);p=int(z[0]);target=int(z[8])
        if d>=0:
            safe[i,FRONTIER+1]=(target%80-p%80)/80;safe[i,FRONTIER+2]=(target//80-p//80)/70
            safe[i,FRONTIER+3]=int(z[9])/150;safe[i,FRONTIER+7:FRONTIER+15]=0;safe[i,FRONTIER+7+d]=1
            grid=z[32:];unknown=[(dx,dy) for dx,dy in [(0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)] if 0<=target%80+dx<80 and 0<=target//80+dy<70 and grid[target+dx+dy*80]==0]
            safe[i,FRONTIER+4]=len(unknown)/8
            if unknown:safe[i,FRONTIER+5:FRONTIER+7]=torch.tensor(unknown[0],device='cuda')
    variants['safe_frontier']=safe
    results={}
    for name,obs in variants.items():
        d=m(obs,mask)[0];p=d.probs.cpu();actions=d.greedy().cpu()
        results[name]=[dict(wait=float(p[i,16]),move=float(p[i,:8].sum()),action=int(actions[i])) for i in range(n)]
    rows=[]
    for i,z in enumerate(raw):
        direction=int(z[4]);legal=direction>=0 and bool(mask[i,direction]);alt=int(z[10])
        rows.append(dict(**b['rows'][i],player=int(z[0]),enemy=int(z[1]),frontier=int(z[2]),frontier_distance=int(z[3]),frontier_direction=direction,frontier_move_legal=legal,frontier_route_wakes=bool(z[7]),safe_frontier=int(z[8]),safe_frontier_direction=alt,safe_frontier_distance=int(z[9]),hidden_safe_exit_count=int(z[11]),legal_moves=int(mask[i,:8].sum()),safe_legal_moves=[j for j in range(8) if mask[i,j] and not z[20+j]],interventions={k:v[i] for k,v in results.items()}))
    output=dict(rows=rows,summary={k:dict(mean_wait=sum(v['wait'] for v in rs)/n,greedy_waits=sum(v['action']==16 for v in rs)) for k,rs in results.items()},notes=['Observation changes are diagnostic counterfactuals, not simulator changes.','Safe routes use exact monster wake LOS; hidden safe-exit counts are oracle diagnostics only.','27 selected WAIT stalls, not all timeout cases.'])
    runners=[]
    for row in rows:
        p=row['probs'];order=sorted(range(19),key=lambda j:p[j],reverse=True)
        assert order[0]==16 and order[1]<8
        action=order[1];move=sum(p[:8])
        runners.append(dict(episode=row['episode'],action=action,probability=p[action],move_type_probability=move,
            conditional_direction_probability=p[action]/move,avoids_waking_sleeper=action in row['safe_legal_moves'],
            follows_original_frontier=action==row['frontier_direction'],follows_safe_frontier=action==row['safe_frontier_direction']))
    output['runner_up_actions']=runners
    (r.SUITE/'stall-inspection.json').write_text(json.dumps(output,indent=2));print(json.dumps(output['summary'],indent=2))
    print('geometry', {k:sum(bool(x[k]) for x in rows) for k in ['frontier_move_legal','frontier_route_wakes','hidden_safe_exit_count']},'safe_frontier',sum(x['safe_frontier_direction']>=0 for x in rows))

FRONTIER=718
if __name__=='__main__':main()
