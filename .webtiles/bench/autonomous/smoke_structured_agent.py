"""Live V6 collection, cloning, learning, checkpoint and inference check."""
import os
os.environ['DCSS_REPRESENTATION']='spatial-v6'
import argparse
import json
import time
from pathlib import Path
import torch
from general_env import GeneralEnvironment
from model import ActionValueModel, tensor_for_actions, save_model, load_model
from teacher import choose_action
from train_model import train_behavioral_clone, train_q_finetune, train_return_policy, _annotate_n_step
from features import FEATURE_VERSION
from collect import run_episode


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=args.output.resolve(); root.mkdir(parents=True,exist_ok=False)
    torch.set_num_threads(1); torch.manual_seed(17)
    rows=[]
    with GeneralEnvironment(root/'game', seed='1760771545328102746') as env:
        state=env.launch()
        assert 'piety_rank' in state['player'] and 'history' in state
        for i in range(64):
            if state.get('terminal'): break
            index=choose_action(state); action=state['actions'][index]
            next_state=env.step(index)
            rows.append({'observation':state,'next_observation':next_state,
                         'action_index':index,'teacher_action_index':index,
                         'policy_version':'teacher','behavior_probability':1.,
                         'score_before':state.get('score'),'score_after':next_state.get('score'),
                         'terminal':bool(next_state.get('terminal'))})
            state=next_state
        assert not state.get('terminal'), 'smoke seed died before snapshot'
        checkpoint=root/'snapshot'
        env.save_state(checkpoint)
        index=choose_action(state)
        first=env.step(index)
        restored=env.restore_state(checkpoint)
        assert restored['history']==state['history']
        second=env.step(index)
        # Feature equality includes history; RNG equality independently checks
        # the engine state, including welcome-message restore regressions.
        a,b=tensor_for_actions(first,first['actions']),tensor_for_actions(second,second['actions'])
        assert all(torch.equal(x,y) for x,y in zip(a,b)), 'feature restore divergence'
        assert first.get('rng_state')==second.get('rng_state'), 'RNG restore divergence'
    for row in rows: row['return']=state.get('score',0)
    _annotate_n_step(rows,{'score':state.get('score',0)})
    model=ActionValueModel()
    initial={k:v.clone() for k,v in model.state_dict().items()}
    started=time.perf_counter()
    model,bc=train_behavioral_clone(rows,epochs=1,model=model)
    critic=train_q_finetune(model,rows[:16])
    actor=train_return_policy(model,rows[:16],epochs=1)
    training_seconds=time.perf_counter()-started
    assert any(not torch.equal(initial[k],v) for k,v in model.state_dict().items())
    path=root/'model.pt'; save_model(path,model,{'smoke':True})
    loaded,_=load_model(path)
    inputs=tensor_for_actions(state,state['actions'])
    torch.testing.assert_close(model(inputs),loaded(inputs))
    started=time.perf_counter()
    with torch.no_grad():
        for _ in range(20): loaded(inputs)
    forward_ms=1000*(time.perf_counter()-started)/20
    started=time.perf_counter()
    with torch.no_grad():
        for _ in range(10): loaded(tensor_for_actions(state,state['actions']))
    decision_ms=1000*(time.perf_counter()-started)/10
    live_actor=run_episode(root/'learned_actor','1760771545328102747',16,
                          model_path=path,epsilon=0,policy_version='v6-smoke',
                          snapshot=False,total_steps=16)
    assert not live_actor.get('error'), live_actor
    assert live_actor.get('steps',0)>0
    result={'feature_version':FEATURE_VERSION,'transitions':len(rows),
            'snapshot_feature_and_rng_deterministic':True,'reload_equal':True,
            'training_seconds':training_seconds,'forward_ms':forward_ms,
            'encoding_and_forward_ms':decision_ms,'live_actor':live_actor,
            'parameters':sum(p.numel() for p in loaded.parameters()),
            'state_dimensions':inputs[0].shape[1],'action_dimensions':inputs[1].shape[1],
            'encoded_bytes':sum(t.numel()*t.element_size() for t in inputs),
            'bc':bc,'critic':critic,'actor':actor}
    (root/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
