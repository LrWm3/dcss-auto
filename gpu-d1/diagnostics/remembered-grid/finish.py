"""Frozen held-out evaluation and paired observation diagnostic. No training."""
from run import evaluate,save_json
from runtime import OUT,ROOT,HERE,Policy,SpatialPolicy
from probes import generate as make_probes,evaluate as probe
import torch,json,hashlib,time

def main():
    torch.set_num_threads(1);torch.manual_seed(11977);torch.backends.cudnn.benchmark=True
    report=dict(schema=1,seed=0,deadlines=dict(validation=256,test=256,long=512),time_input_scale=2048,semantics=json.loads((OUT/'semantics.json').read_text()),arms={},default_reset_check=json.loads((OUT/'default-reset-check.json').read_text()),notes=[
        'Supervised imitation plus corrective labels, no PPO.',
        '32x32 synthetic floors, production movement/LOS/combat. Not ordinary D1 performance.',
        'No frontier/stair arrows, route distances, or teacher actions at learned-policy evaluation.',
        '256 physical turns for validation/test; 512 for long routes; both include real observation history.',
        'One seed; geometry/placement uncertainty is not training-seed uncertainty.',
        'Simple pressure fixtures alone may be solvable without enemy memory; inspect controls.',
        'Early CNN/U-net timing included validation environment setup overhead; later arms exclude it.'
    ])
    make_probes();torch.manual_seed(0);random=SpatialPolicy().cuda()
    z=evaluate(random);report['untrained_validation']=z;print('untrained',z['summary'],flush=True)
    report['teacher']={}
    for split in ['validation','test','long']:
        z=evaluate(random,split,teacher=True);report['teacher'][split]=z;print('teacher',split,z['summary'],flush=True)
    for name in ['memory','memory-spatial','local-spatial','terrain-spatial']:
        folder=OUT/name;path=folder/('best.pt' if (folder/'best.pt').exists() else 'latest.pt');ck=torch.load(path,weights_only=False)
        cls=SpatialPolicy if ck.get('architecture')=='spatial' else Policy;model=cls(ck['arm']).cuda();model.load_state_dict(ck['model']);model.eval()
        arm=dict(parameters=sum(p.numel() for p in model.parameters()),checkpoint_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),checkpoint_step=ck['step'],training=json.loads((folder/'training.json').read_text()),evaluations={})
        if (folder/'selection.json').exists():arm['selection']=json.loads((folder/'selection.json').read_text())
        for split in ['test','long']:
            for mode in ['greedy','sampled']:
                torch.manual_seed(11977);z=evaluate(model,split,mode=mode);arm['evaluations'][split+'_'+mode]=z;print(name,split,mode,z['summary'],flush=True)
        arm['goal_probe']=probe(model)
        if name=='memory-spatial':
            arm['goal_probe_without_global']=probe(model,intervene='erase_global')
            arm['without_enemy_memory']=evaluate(model,'test',intervene='erase_memory')
        report['arms'][name]=arm
        save_json(OUT/'final.json',report)
    report['complete']=True
    save_json(OUT/'final.json',report);save_json(ROOT/'results/remembered-grid.json',report)
    print('COMPLETE',flush=True)
if __name__=='__main__':main()
