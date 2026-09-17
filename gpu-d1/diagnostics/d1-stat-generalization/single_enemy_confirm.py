"""Fresh-roll confirmation of nominal and weak-player/strong-enemy duels."""
import json
import time
import torch
import single_enemy as s

def main():
    torch.set_num_threads(1);started=time.monotonic()
    assert (s.OUT/'result.json').exists()
    s.build()
    profiles=[p['id'] for p in s.r.SPEC['profiles'] if p['values'] in [[18,4,1.,1.,24],[12,3,1.25,1.25,24]]]
    bank=s.collect(profiles)
    ids=[i for i,row in enumerate(bank['rows']) if row['kind'] in [3,4]]
    bank={k:v[ids] if isinstance(v,torch.Tensor) else [v[i] for i in ids] for k,v in bank.items()}
    e=s.Env(4096);result=dict(states=bank['rows'],controllers={},note='Fresh combat RNG seeds after the broad screen. Fixed nominal and weak-player/strong-enemy profiles, kinds3/4, both geometries and all starting HP levels. No new geometry selection.')
    for mode,name in enumerate(['fight','heal_then_fight','bypass','escape_adjacent']):
        result['controllers'][name]=s.controller(e,bank,mode,repeats=4096,seed=92719101,independent_states=True)
        print(name,flush=True)
    result['seconds']=time.monotonic()-started
    (s.OUT/'confirmation.json').write_text(json.dumps(result,indent=2)+'\n')
    (s.r.ROOT/'results/d1-single-enemy-confirmation.json').write_text(json.dumps(result,indent=2)+'\n')
    print('confirmation_complete',result['seconds'],flush=True)

if __name__=='__main__':main()
