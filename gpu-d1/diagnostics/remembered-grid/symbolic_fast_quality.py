import torch
from run import evaluate,save_json
from runtime import ROOT
from optimize_symbolic import load
from symbolic_policy import Stateful
class PrecisionState(Stateful):
    def __init__(self,model,amp):super().__init__(model);self.amp=amp
    def __call__(self,*args,**kwargs):
        with torch.autocast('cuda',dtype=torch.float16,enabled=self.amp):return super().__call__(*args,**kwargs)
def main():
    torch.set_num_threads(1);torch.manual_seed(11812);torch.backends.cudnn.benchmark=True;out={}
    for amp in [False,True]:
        m=load(True);out[str(amp)]={}
        for split in ['test','long']:
            z=evaluate(PrecisionState(m,amp),split);out[str(amp)][split]=z;print('AMP',amp,split,z['summary'],flush=True)
    save_json(ROOT/'results/symbolic-optimization-quality.json',out)
if __name__=='__main__':main()
