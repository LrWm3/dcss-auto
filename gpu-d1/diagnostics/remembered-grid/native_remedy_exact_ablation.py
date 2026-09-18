"""Measure reliance on the learned exact-map residual after its training run."""
import hashlib
import torch
from native_remedies import make_model
from native_curriculum import factory
from run import evaluate,save_json
from runtime import OUT,ROOT
from fullsize_navigation import FullEnv,build_full
from symbolic_execution import PolicyExecution,StaticInference

def main():
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True;build_full()
    source=OUT/'native-remedy-exact/selected.pt';state=torch.load(source,weights_only=False)['model']
    model=make_model(True);model.load_state_dict(state)
    report=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),scope='Zero exact residual output after training. Old coarse branch and other trained weights remain. Out-of-distribution reliance check, not a separately trained capacity control.')
    with torch.no_grad():model.exact[-1].weight.zero_();model.exact[-1].bias.zero_()
    policy=StaticInference(PolicyExecution(model,compiled=True),amp=True,graphed=True)
    for label,env,split in [('middle_validation',factory(1),'validation'),('full_test',FullEnv,'test')]:
        torch.manual_seed(11812);report[label]=evaluate(policy,split,env_class=env,limit=1024)
        print(label,report[label]['summary'],flush=True)
    save_json(ROOT/'results/native-remedy-exact-ablation.json',report)
if __name__=='__main__':main()
