"""Frozen regression evaluation of the cheaper encoder; no fitting on test maps."""
import json,torch,hashlib,argparse
from run import evaluate
from runtime import PackedPolicy,Packed2Policy,CroppedSpatialPolicy,ThinSpatialPolicy,OUT,ROOT
from probes import evaluate as probe,generate

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--architecture",choices=["packed","packed2","cropped","thin"],default="packed");ap.add_argument("--compile",action="store_true");args=ap.parse_args()
    torch.set_num_threads(1);torch.manual_seed(11977);torch.backends.cudnn.benchmark=True
    folder=OUT/('terrain-'+('spatial' if args.architecture=='cropped' else args.architecture));checkpoint=folder/'best.pt';ck=torch.load(checkpoint,weights_only=False)
    model=({'packed':PackedPolicy,'packed2':Packed2Policy,'cropped':CroppedSpatialPolicy,'thin':ThinSpatialPolicy}[args.architecture])('terrain').cuda().to(memory_format=torch.channels_last);model.load_state_dict(ck['model']);model.eval()
    if args.compile:
        if hasattr(model,'fast_pool'):model.fast_pool=True
        model.compile(fullgraph=True)
    result=dict(compiled=args.compile,architecture=args.architecture,weights_reused_without_training=args.architecture=='cropped',checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),checkpoint_step=ck['step'],training=json.loads((folder/'training.json').read_text()),evaluations={},notes=['One seed; original held-out suite now serves as a regression suite.','32x32 learning quality; full-map benchmark measures compute only.','Terrain-only enemy knowledge; no remembered-enemy benefit claimed.'])
    for split in ['test','long']:
        for mode in ['greedy','sampled']:
            torch.manual_seed(11977);value=evaluate(model,split,mode=mode);result['evaluations'][split+'_'+mode]=value;print(split,mode,value['summary'],flush=True)
    generate();result['goal_probe']=probe(model)
    (ROOT/('results/remembered-grid-'+args.architecture+'.json')).write_text(json.dumps(result,indent=2)+'\n')
    print('probe',result['goal_probe'],flush=True)
if __name__=='__main__':main()
