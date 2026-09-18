"""Post-training diagnostic of global visited-history use by the original model."""
import hashlib,json,torch
from run import evaluate,save_json
from runtime import SpatialPolicy,OUT,ROOT

def main():
    torch.set_num_threads(1);torch.manual_seed(11977);torch.backends.cudnn.benchmark=True
    path=OUT/'terrain-spatial/best.pt';m=SpatialPolicy('terrain').cuda();ck=torch.load(path,weights_only=False);m.load_state_dict(ck['model']);m.eval()
    baseline=evaluate(m,'test')
    # The local crop is computed before fine(), so it keeps its visited channel.
    def erase(module,args):
        g=args[0].clone();g[:,2]=0;return (g,)
    handle=m.fine.register_forward_pre_hook(erase)
    try:erased=evaluate(m,'test')
    finally:handle.remove()
    result=dict(scope='Post-training observation intervention, not retraining. Removes only the global visited channel at the first global convolution; local visited observations, visibility, player marker, terrain and coordinates remain unchanged.',checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),selected_update=ck['step'],baseline=baseline,global_visits_erased=erased,interpretation='A drop demonstrates reliance under an out-of-distribution intervention; it does not establish what a retrained model could do without this input.')
    save_json(ROOT/'results/remembered-grid-global-visits-ablation.json',result)
    print(json.dumps({k:result[k]['summary'] for k in ['baseline','global_visits_erased']}),flush=True)
if __name__=='__main__':main()
