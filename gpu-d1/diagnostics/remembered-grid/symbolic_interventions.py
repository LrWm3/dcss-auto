"""Post-training global-map reliance, preserving recurrent state during rollout."""
import hashlib,torch
from run import evaluate,save_json
from runtime import OUT,ROOT,Env
from compact_policy import crop
import probes
from symbolic_policy import SymbolicPolicy,Stateful

def main():
    torch.set_num_threads(1);torch.manual_seed(11812);torch.backends.cudnn.benchmark=True
    path=OUT/'symbolic-gru/best.pt';ck=torch.load(path,weights_only=False);m=SymbolicPolicy(True).cuda();m.load_state_dict(ck['model'])
    result=evaluate(Stateful(m),'test',intervene='erase_global')
    probes.generate();e=Env('probe',48);e.reset(torch.arange(48,device='cuda'),seed=127)
    local=crop(e.grid,e.stats[:,2:4],m.offsets)
    assert torch.equal(local[::2],local[1::2]);assert torch.equal(e.stats[::2],e.stats[1::2])
    pairs={}
    with torch.no_grad():
        for condition in [None,'erase_global']:
            logits=Stateful(m)(e.grid,e.mask,e.stats,condition);a=logits.argmax(-1);correct=a==e.labels
            pairs[condition or 'normal']=dict(initial_correct=float(correct.float().mean()),both_in_pair_correct=int(correct.reshape(24,2).all(1).sum()),pairs=24,actions=a.tolist(),teacher_actions=e.labels.tolist())
    save_json(ROOT/'results/remembered-grid-symbolic-interventions.json',dict(checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),selected_update=ck['step'],global_erased=result,paired_initial_goal_actions=pairs,scope='Post-training OOD intervention: zero the entire encoded global map, including player and stairs channels. Retain local terrain, tactical observations and recurrent memory. Does not establish what retraining without global input could achieve.'))
    print(result['summary'],flush=True)
if __name__=='__main__':main()
