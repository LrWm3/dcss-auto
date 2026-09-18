"""Frozen branch diagnostics on train and held-out layouts."""
import json
import torch
from run import evaluate,save_json
from native_cached_exact import make_model,CachedInference
from native_curriculum import factory
from fullsize_navigation import FullEnv,build_full
from runtime import ROOT,OUT

def main():
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True;build_full()
    name='native-cached-frozen-seed0';path=ROOT/'results'/f'{name}.json'
    report=json.loads(path.read_text());assert report['finished'] and report['frozen_parameters_unchanged']
    report['diagnostics']={}
    def assess(label,model,split,cls,intervene=None):
        result=evaluate(CachedInference(model),split,limit=1024,env_class=cls,intervene=intervene)
        report['diagnostics'][label]=result;save_json(path,report)
        print(label,result['summary'],flush=True)
    source=make_model()
    assess('source_train',source,'train',factory(1))
    joint=make_model();joint.load_state_dict(torch.load(OUT/'native-cached-exact-seed0/selected.pt',weights_only=False)['model'])
    assess('joint_train',joint,'train',factory(1))
    model=make_model();model.load_state_dict(torch.load(OUT/name/'selected.pt',weights_only=False)['model'])
    assess('frozen_train',model,'train',factory(1))
    # Erasure should exactly restore the original model; compare ordinary
    # FP32 feature outputs to catch accidental changes outside the new branch.
    env=factory(1)('validation',32);env.reset(seed=71)
    with torch.no_grad():
        a=model.encode(env.grid,env.stats,'erase_exact');b=source.encode(env.grid,env.stats)
        torch.testing.assert_close(a,b,atol=1e-6,rtol=1e-5)
    report['erasure_restores_source_features']=True
    assess('frozen_erased_middle_test',model,'test',factory(1),'erase_exact')
    assess('frozen_erased_full_test',model,'test',FullEnv,'erase_exact')
    assess('frozen_shuffled_validation',model,'validation',factory(1),'shuffle_exact')
    report['diagnostic_scope']='Train maps versus held-out tests; erasure checks branch contribution. Shuffled-map intervention deliberately breaks observation consistency and measures sensitivity, not correct geometric reasoning.'
    report['diagnostics_finished']=True;save_json(path,report)

if __name__=='__main__':main()
