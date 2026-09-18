"""Compare truncated recurrent replay to live rollout on identical observations."""
import torch
from native_remedies import make_model
from native_curriculum import factory
from run import save_json
from runtime import OUT,ROOT
from fullsize_navigation import build_full
from symbolic_execution import PolicyExecution

@torch.no_grad()
def check(source,exact=False):
    model=make_model(exact);model.load_state_dict(torch.load(source,weights_only=False)['model'])
    execution=PolicyExecution(model,compiled=True);env=factory(1)('train',32)
    totals={str(k):dict(states=0,action_disagreements=0,kl=0.,teacher_nll=0.,live_teacher_nll=0.) for k in (16,31,64,'full')}
    for wave in range(2):
        torch.manual_seed(9123+wave);env.reset(seed=822+wave);h=torch.zeros(32,128,device='cuda');history=[]
        for tick in range(512):
            with torch.autocast('cuda',dtype=torch.float16):
                x=execution.features(env.grid,env.stats);h=model.core(x,h);logits,_=execution.heads(h,env.mask)
            history.append(x.clone())
            if tick>=64 and tick%16==0:
                active=env.active.clone();count=int(active.sum())
                if count:
                    live=torch.distributions.Categorical(logits=logits,validate_args=False)
                    for horizon in (16,31,64,'full'):
                        segment=history if horizon=='full' else history[-(horizon+1):]
                        with torch.autocast('cuda',dtype=torch.float16):
                            z,_=model.sequence(torch.stack(segment,1));replayed,_=execution.heads(z[:,-1],env.mask)
                        replay=torch.distributions.Categorical(logits=replayed,validate_args=False)
                        r=totals[str(horizon)];r['states']+=count;r['action_disagreements']+=int(((replayed.argmax(-1)!=logits.argmax(-1))&active).sum())
                        r['kl']+=float(torch.distributions.kl_divergence(live,replay)[active].sum())
                        r['teacher_nll']+=float(-replay.log_prob(env.labels)[active].sum());r['live_teacher_nll']+=float(-live.log_prob(env.labels)[active].sum())
            env.step(logits.argmax(-1),limit=1024)
            if not env.active.any():break
    for r in totals.values():
        for k in ('kl','teacher_nll','live_teacher_nll'):r[k]/=max(1,r['states'])
        r['action_disagreement_fraction']=r['action_disagreements']/max(1,r['states'])
    return totals

def main():
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True;build_full()
    report=dict(scope='Read-only probe of greedy middle-band training trajectories, fixed parameters. Compare live cell execution against 16/31/64-step burn-in and full-history fused replay; measured every16 steps after64. All share identical encoded observations. This is not a longer-memory training experiment.')
    for label,path,exact in [('source',OUT/'native-curriculum-seed0/selected.pt',False),('balanced',OUT/'native-remedy-balanced/selected.pt',False),('exact',OUT/'native-remedy-exact/selected.pt',True)]:
        report[label]=check(path,exact);print(label,report[label],flush=True)
        save_json(ROOT/'results/native-replay-audit.json',report)
if __name__=='__main__':main()
