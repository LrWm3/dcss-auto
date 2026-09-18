"""Matched short DAgger screen; cached inference, fresh differentiable replay."""
import sys
import torch
import native_remedies as runner
from native_cached_exact import make_model,CachedInference

if __name__=='__main__':
    frozen='--freeze-base' in sys.argv
    if frozen:sys.argv.remove('--freeze-base')
    old_make=runner.make_model
    tracked={}
    def create(exact=False):
        if not exact:return old_make(False)
        model=make_model()
        if frozen:
            for name,p in model.named_parameters():
                p.requires_grad_(name.startswith(('map_encoder.','map_readout.')))
            tracked['before']={k:v.detach().clone() for k,v in model.state_dict().items()}
            tracked['model']=model
        return model
    runner.make_model=create
    runner.StaticInference=lambda execution,**kwargs: CachedInference(execution.model)
    original_save=runner.save_json
    def save(path,report):
        report['frozen_base']=frozen
        if frozen:
            model=tracked['model'];state=model.state_dict();before=tracked['before']
            old=[k for k in state if not k.startswith(('map_encoder.','map_readout.'))]
            assert all(torch.equal(state[k],before[k]) for k in old),'Frozen parameter changed'
            report['frozen_parameters_unchanged']=True
            report['new_branch_changed']=any(not torch.equal(state[k],before[k]) for k in state if k not in old)
            report['branch_modules_changed']={prefix:any(not torch.equal(state[k],before[k]) for k in state if k.startswith(prefix+'.')) for prefix in ['map_encoder','map_readout']}
            report['trainable_parameters']=sum(p.numel() for p in model.parameters() if p.requires_grad)
            report['scope']='Only exact-map encoder/readout train; original local/global/tactical encoders, GRU, policy and value heads remain frozen. Same middle-band balanced DAgger screen; not PPO.'
        original_save(path,report)
    runner.save_json=save
    sys.argv+=['--arm','exact']
    runner.main()
