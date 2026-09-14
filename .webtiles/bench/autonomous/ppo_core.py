"""On-policy PPO over ragged legal actions; undiscounted score differences.

The existing separate critic encoder is used as V(s), with zero action inputs.
No old Q/log-score critic targets or optimizer states are compatible with this.
"""
import copy
import math
import random
import statistics

import torch
from torch import nn

from model import tensor_for_actions
from teacher import _actions
from exploration_score import learning_score


VERSION = 'ragged-ppo-score-deltas-v1'
SCALE = 1000.


def reward_delta(before, after):
    if before.get('score_version') != after.get('score_version'):
        raise ValueError('mixed score objectives')
    a, b = learning_score(before), learning_score(after)
    if any(v is None or not math.isfinite(v) for v in (a,b)):
        raise ValueError('invalid score transition')
    return (b-a)/SCALE


def state_value(model, x):
    states, actions = x
    zeros = actions.new_zeros((len(states), actions.shape[-1]))
    owners = torch.arange(len(states))
    return model.value_net.packed(states, zeros, owners)


def initialise_critic(model):
    # Reuse the competent visual representation, not the old log-score head.
    model.value_net.load_state_dict(model.net.state_dict())
    nn.init.zeros_(model.value_net.head[-1].weight)
    nn.init.zeros_(model.value_net.head[-1].bias)


def distribution(model, state):
    x = tensor_for_actions(state, _actions(state))
    with torch.no_grad():
        logp = model(x).log_softmax(0)
        value = float(state_value(model,x)[0])
    if not torch.isfinite(logp).all() or not math.isfinite(value):
        raise ValueError('nonfinite policy/value output')
    return logp, value


def sample(logp, rng):
    return rng.choices(range(len(logp)), weights=logp.exp().tolist(), k=1)[0]


def advantages(rows, lam=.95):
    """segment_end cuts GAE recurrence, not bootstrap; terminal bootstrap = 0."""
    out = [0.]*len(rows)
    carry = 0.
    for i in range(len(rows)-1,-1,-1):
        r=rows[i]
        if r['segment_end']:
            carry=0.
        bootstrap=0. if r['terminated'] else r['next_value']
        residual=r['reward']+bootstrap-r['value']  # gamma = 1
        carry=residual+lam*carry
        out[i]=carry
    return out, [a+r['value'] for a,r in zip(out,rows)]


def pack(cache, indices):
    states=torch.cat([cache[i][0] for i in indices])
    actions=torch.cat([cache[i][1] for i in indices])
    lengths=[len(cache[i][1]) for i in indices]
    owners=torch.repeat_interleave(torch.arange(len(indices)),torch.tensor(lengths))
    return states,actions,owners,lengths


def policy_loss(logp, old_logp, advantage, clip=.1):
    ratio=(logp-old_logp).exp()
    return -torch.minimum(ratio*advantage,ratio.clamp(1-clip,1+clip)*advantage).mean()


def fit_ppo(model, rows, actor_opt, critic_opt, seed, epochs=4, batch_size=32):
    if len(rows)<16:
        return {'updated': False, 'reason': 'too few valid transitions'}
    cache=[tensor_for_actions(r['observation'],_actions(r['observation'])) for r in rows]
    old=[torch.tensor(r['log_probs']) for r in rows]
    selected=torch.tensor([r['action_index'] for r in rows])
    raw_adv, raw_targets=advantages(rows)
    adv=torch.tensor(raw_adv)
    adv=(adv-adv.mean())/adv.std(unbiased=False).clamp_min(1e-6)
    targets=torch.tensor(raw_targets)
    rng=random.Random(seed)
    order=list(range(len(rows)))

    def audit():
        kls=[]
        with torch.no_grad():
            for start in range(0,len(rows),batch_size):
                ids=list(range(start,min(start+batch_size,len(rows))))
                s,a,o,lengths=pack(cache,ids)
                logits=model.net.packed(s,a,o)
                for i,part in zip(ids,logits.split(lengths)):
                    kls.append(float((old[i].exp()*(old[i]-part.log_softmax(0))).sum()))
        return {'mean_kl':statistics.mean(kls),'max_kl':max(kls)}

    initial=audit()
    if initial['max_kl']>1e-4:
        raise ValueError('PPO batch was not collected by current policy')
    history=[]
    for epoch in range(epochs):
        saved=copy.deepcopy(model.state_dict())
        saved_actor=copy.deepcopy(actor_opt.state_dict())
        saved_critic=copy.deepcopy(critic_opt.state_dict())
        rng.shuffle(order)
        pl,vl,ent=[],[],[]
        for start in range(0,len(rows),batch_size):
            ids=order[start:start+batch_size]
            s,a,o,lengths=pack(cache,ids)
            logits=model.net.packed(s,a,o)
            parts=[p.log_softmax(0) for p in logits.split(lengths)]
            chosen=torch.stack([p[selected[i]] for i,p in zip(ids,parts)])
            prior=torch.stack([old[i][selected[i]] for i in ids])
            entropy=torch.stack([-(p.exp()*p).sum() for p in parts]).mean()
            loss=policy_loss(chosen,prior,adv[ids])-.001*entropy
            actor_opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.net.parameters(),.5)
            actor_opt.step()
            values=state_value(model,(s,a))
            value_loss=nn.functional.mse_loss(values,targets[ids])
            critic_opt.zero_grad()
            value_loss.backward()
            torch.nn.utils.clip_grad_norm_(model.value_net.parameters(),.5)
            critic_opt.step()
            pl.append(float(loss.detach()));vl.append(float(value_loss.detach()));ent.append(float(entropy.detach()))
        check=audit()
        accepted=(math.isfinite(check['mean_kl']) and check['mean_kl']<=.01
                  and check['max_kl']<=.15 and all(torch.isfinite(p).all() for p in model.parameters()))
        history.append({'epoch':epoch+1,**check,'accepted':accepted,
                        'policy_loss':statistics.mean(pl),'value_loss':statistics.mean(vl),
                        'entropy':statistics.mean(ent)})
        if not accepted:
            model.load_state_dict(saved)
            actor_opt.load_state_dict(saved_actor)
            critic_opt.load_state_dict(saved_critic)
            break
    model.eval()
    return {'updated':any(h['accepted'] for h in history),'transitions':len(rows),
            'epochs':history,'audit':audit(),'mean_reward':statistics.mean(r['reward'] for r in rows),
            'return_target_mean':statistics.mean(raw_targets),'version':VERSION,
            'gamma':1.,'lambda':.95,'score_scale':SCALE}
