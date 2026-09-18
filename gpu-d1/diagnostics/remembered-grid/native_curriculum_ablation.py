"""Post-training global-feature ablation on the original native test cases."""
import hashlib
import torch
from run import evaluate, save_json
from runtime import OUT, ROOT
from fullsize_navigation import FullEnv, build_full
from optimize_symbolic import load
from symbolic_execution import StaticInference
from symbolic_fullsize_diagnostic import DiagnosticExecution

def main():
    torch.set_num_threads(1);torch.backends.cudnn.benchmark=True;build_full()
    path=OUT/'native-curriculum-seed0/selected.pt'
    model=load(True).configure_encoder(True,True)
    model.load_state_dict(torch.load(path,weights_only=False)['model'])
    report=dict(source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),scope='Matched greedy rollouts; erasing the global encoded feature is an out-of-distribution intervention, not a trained local-only control.')
    for arm in ('normal','erase_global'):
        torch.manual_seed(11812)
        policy=StaticInference(DiagnosticExecution(model,arm),amp=True,graphed=True)
        report[arm]=evaluate(policy,'test',env_class=FullEnv,limit=1024)
        print(arm,report[arm]['summary'],flush=True)
        save_json(ROOT/'results/native-curriculum-global-ablation.json',report)
    report['finished']=True
    save_json(ROOT/'results/native-curriculum-global-ablation.json',report)
if __name__=='__main__':main()
