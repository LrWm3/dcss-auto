"""Held-out tactical evaluation, always at normal policy temperature."""
import pathlib
import torch
from tactical_env import TacticalEnv
FAMILIES=['hallway','diagonal_pocket','passing_enemy','separated_groups']


@torch.no_grad()
def evaluate_tactics(model,job,controls=False):
    env=TacticalEnv(512,24,seed=830001,corpus=pathlib.Path(job['tactical_eval_corpus']),map_limit=64,map_filter=-2,library_path=job['tactical_library'])
    result={}
    with torch.random.fork_rng(devices=[0]):
        for mode in (['teacher','cover'] if controls else ['sampled','greedy']):
            torch.manual_seed(7139);env.reset(830001)
            _,initial=env.probe();initial=initial.clone()
            active=torch.ones(env.batch,dtype=torch.bool,device='cuda');terminal=torch.zeros_like(env.out)
            reached=torch.zeros_like(active);multiple=torch.zeros(env.batch,device='cuda');contact=multiple.clone();waiting=multiple.clone();ret=multiple.clone();first_move=None
            for step in range(2048):
                script,stats=env.probe(int(mode=='cover'))
                reached|=active&stats[:,5].bool();multiple+=active&(stats[:,2]>1);contact+=active&(stats[:,2]>0)
                if mode in ['teacher','cover']:a=script
                else:
                    dist,_=model(env.obs,env.mask);a=dist.sample() if mode=='sampled' else dist.greedy()
                    if step==0:first_move=dist.probs[:,:8].sum(1).clone()
                assert bool(((env.mask.gather(1,a[:,None]).squeeze(1)>0)|~active).all())
                waiting+=active&(stats[:,2]>0)&(a==16)
                env.step(a,active=active);ret+=active*env.out[:,40];ended=active&(env.out[:,1]>0)
                terminal[ended]=env.out[ended];active&=~ended
                if not active.any():break
            assert not active.any()
            torch.testing.assert_close(ret,terminal[:,2]-.00001*terminal[:,5],atol=1e-4,rtol=0)
            def summarize(sel):
                if not sel.any():return dict(episodes=0,clear=None,death=None,timeout=None,turns=None,return_mean=None,reached_cover=None,multi_adjacent_turns=None,wait_when_adjacent=None,first_move_probability=None)
                t=terminal[sel];c=contact[sel].sum()
                return dict(episodes=int(sel.sum()),clear=float(t[:,2].mean()),death=float(t[:,6].mean()),timeout=float(t[:,7].mean()),turns=float(t[:,5].mean()),return_mean=float(ret[sel].mean()),reached_cover=float(reached[sel].float().mean()),multi_adjacent_turns=float(multiple[sel].mean()),wait_when_adjacent=float(waiting[sel].sum()/c) if c else None,first_move_probability=float(first_move[sel].mean()) if first_move is not None else None)
            result[mode]=dict(overall=summarize(torch.ones_like(active)),families={name:summarize(initial[:,7]==i) for i,name in enumerate(FAMILIES)},pressure=summarize(initial[:,6]>1),easy=summarize(initial[:,6]==1),episodes=dict(clear=terminal[:,2].cpu().tolist(),turns=terminal[:,5].cpu().tolist(),family=initial[:,7].cpu().tolist(),initial_hp=initial[:,0].cpu().tolist(),initial_enemies=initial[:,6].cpu().tolist()))
    return result
