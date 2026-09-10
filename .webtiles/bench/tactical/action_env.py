"""V1 action-level Gym environment. No scripted combat or automatic rest.

One request is a direction/bump attack, wait, or berserk. Rejected requests are
explicit no-ops, not silently replaced with a scripted action. Harness errors
raise; they must never become negative gameplay training examples.
"""
from collections import Counter, deque
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import re
import time
import pexpect

import gymnasium as gym
import numpy as np

import bench
from cached_env import CachedEnvironment
from experiment import DIRECTIONS
from goal_controllers import Recovery, geometry, dist, paths, ranged_danger
from rich_features import features, values

ACTIONS = tuple(DIRECTIONS) + ('wait', 'berserk')
BINS = 8192
HISTORY = 4
FRAME_SIZE = BINS+len(ACTIONS)+4

class ActionTransport(CachedEnvironment):
    def close(self):
        try:
            return super().close()
        except pexpect.ExceptionPexpect as exc:
            if str(exc) != 'Could not terminate the child.':
                raise
            # PTY close already sent SIGKILL, but its short status poll can race
            # process exit under load. Only wait for this owned child; never
            # suppress a genuinely live process or an unrelated close error.
            deadline = time.monotonic()+3
            while self.child.isalive():
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.05)
            return super().close()

    def death_record(self):
        # Draining adds an undrained maximum: "-2/56 (61) HPs". Historical
        # parser rejects that valid death. Keep this fix in the new adapter.
        for path in (self.work/'morgue').glob('morgue-'+bench.NAME+'-*.txt'):
            content=path.read_text(errors='replace')
            header=re.search(r'^.*\b'+re.escape(bench.NAME)+r'\b[^\n]*\(level \d+, (-?\d+)/\d+(?: \(\d+\))? HPs\)',content,re.M)
            turns=re.search(r'\bTurns:\s*(\d+)',content)
            if (header and int(header[1])<=0 and turns
                and int(turns[1])>=getattr(self,'state',{}).get('turn',0)
                and re.search(r'^Game seed: '+re.escape(self.seed)+r'\b',content,re.M)):
                return dict(terminal='death',evidence=str(path),evidence_sha256=bench.sha(path))
        return None

@lru_cache(maxsize=65536)
def feature_slot(key):
    n = int.from_bytes(hashlib.blake2b(key.encode(),digest_size=8).digest(),'little')
    return n % BINS, 1 if n & (1<<63) else -1

def frame(state, last_action=None, hp_delta=0., quiet=0):
    out = np.zeros(FRAME_SIZE,dtype=np.float32)
    if state.get('terminal'):
        return out
    for key,value in features(state).items():
        slot, sign = feature_slot(key)
        out[slot] += sign*value
    np.clip(out[:BINS],-10,10,out=out[:BINS])
    if last_action is not None:
        out[BINS+last_action] = 1
    out[-4:] = [state['hp']/state['max_hp'],hp_delta,quiet/20,1.]
    return out

def legal_mask(s):
    cells = geometry(s)
    hostiles = {(e['x'],e['y']) for e in values(s.get('monsters'))}
    mask = []
    for direction in DIRECTIONS.values():
        c = cells.get(direction,{})
        # Conservative prompt-free subset: no unknown squares, doors needing
        # opening, damaging terrain/cloud prompts, or attacks on known allies.
        usable = bool(c.get('traversable')) and not any(c.get(k) for k in ('withheld','unsafe','excluded'))
        usable = usable and (not c.get('occupied') or direction in hostiles or c.get('invisible_monster'))
        mask.append(usable)
    mask += [True, bool(s.get('can_berserk') and not s.get('berserk')
                       and not s.get('cooldown') and not s.get('confused'))]
    return np.asarray(mask,dtype=bool)

def fixed_action(s, mask, policy='pursue'):
    """Action-matched heuristic baselines, not the historical Tab controllers."""
    enemies = values(s.get('monsters'))
    if policy=='pursue_berserk' and mask[-1] and any(dist((e['x'],e['y']))<=1 for e in enemies):
        return ACTIONS.index('berserk')
    candidates=[]
    routes=paths(s,ignore_occupied=True)
    for e in enemies:
        target=(e['x'],e['y'])
        if target in DIRECTIONS.values():
            action=next(k for k,v in DIRECTIONS.items() if v==target)
            if mask[ACTIONS.index(action)]:
                candidates.append((0,-e['threat'],ACTIONS.index(action)))
        route=routes.get(target)
        if route and mask[ACTIONS.index(route[0])]:
            candidates.append((len(route),-e['threat'],ACTIONS.index(route[0])))
    if candidates:
        return min(candidates)[2]
    return ACTIONS.index('wait')

class ActionEnv(gym.Env):
    metadata = {'render_modes':[]}
    def __init__(self, config, workspace, partition='train', max_steps=192):
        self.config = json.loads(Path(config).read_text())
        self.entries = [e for e in self.config['cases'] if e['split']==partition]
        if not self.entries:
            raise ValueError('Empty partition')
        if partition not in ('train','validation'):
            raise ValueError('Training runner cannot access test')
        seed_sets={p:{e['seed'] for e in self.config['cases'] if e['split']==p}
                   for p in ('train','validation','test')}
        if any(seed_sets[a]&seed_sets[b] for a,b in [('train','validation'),('train','test'),('validation','test')]):
            raise ValueError('Seed leakage')
        bench.ENGINE=Path(self.config['engine'])
        if bench.sha(bench.ENGINE)!=self.config['engine_sha256']:
            raise ValueError('Engine changed')
        os.environ['DCSS_TACTICAL_SIM_FLAGS']='3'
        os.environ['DCSS_TACTICAL_AUGMENT']='1'
        os.environ['DCSS_TACTICAL_CACHE_TEMPLATE']=self.config['cache']
        self.transport=ActionTransport(workspace)
        self.action_space=gym.spaces.Discrete(len(ACTIONS))
        self.observation_space=gym.spaces.Box(-10,10,(FRAME_SIZE*HISTORY,),dtype=np.float32)
        self.max_steps=max_steps
        self.episode=0
        self.finished=True

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        if not self.finished and hasattr(self,'state'):
            self._finish('administrative_reset')
        index=(options or {}).get('case_index')
        if index is None:
            index=int(self.np_random.integers(len(self.entries)))
        self.entry=self.entries[index]
        self.state=self.transport.reset(self.entry['case'])
        self.recovery=Recovery()
        self.steps=0; self.noops=0; self.blocked=set(); self.damage=0; self.actions=Counter()
        self.total_reward=0.; self.finished=False; self.episode+=1
        self.history=deque([np.zeros(FRAME_SIZE,dtype=np.float32) for _ in range(HISTORY-1)],maxlen=HISTORY)
        self.history.append(frame(self.state))
        self.audit=(self.transport.work/'actions.jsonl').open('w')
        self.requests=(self.transport.work/'requests.jsonl').open('w',buffering=1)
        return np.concatenate(self.history),{'case_id':self.entry['id']}

    def action_masks(self):
        mask=legal_mask(self.state)
        for i in self.blocked:
            mask[i]=False
        if not mask.any():
            raise RuntimeError('No actions available; not a gameplay death')
        return mask

    def step(self, action):
        action=int(action)
        if self.finished:
            raise RuntimeError('Reset required')
        mask=self.action_masks()
        if not 0<=action<len(ACTIONS) or not mask[action]:
            raise ValueError('Unavailable action')
        before=self.state
        self.requests.write(json.dumps(dict(before_seq=before['seq'],action=ACTIONS[action]))+'\n')
        try:
            after=self.transport.step(ACTIONS[action])
        except Exception as exc:
            (self.transport.work/'harness-error.json').write_text(json.dumps(dict(
                error=repr(exc),action=ACTIONS[action],before_seq=before['seq'],
                terminal_tail=getattr(self.transport,'terminal_tail','')),indent=2)+'\n')
            self._finish('harness_error')
            raise
        self.steps+=1; self.actions[ACTIONS[action]]+=1
        terminal=after.get('terminal')=='death'
        delta=after.get('turn',before['turn'])-before['turn']
        if not terminal and delta not in (0,1):
            raise RuntimeError(f'Unexpected {delta}-turn command; stop for audit')
        no_op=not terminal and delta==0
        self.noops=self.noops+1 if no_op else 0
        if no_op:
            self.blocked.add(action)
        else:
            self.blocked.clear()
        recovered=self.recovery.observe(before,after) if not terminal else False
        old_fraction=before['hp']/before['max_hp']
        new_fraction=0 if terminal else after['hp']/after['max_hp']
        # Avoid counting removal of berserk's temporary HP as battle damage.
        self.damage+=max(0,old_fraction-new_fraction)*min(before['max_hp'],after.get('max_hp',before['max_hp']))
        # Potential-based HP shaping (same gamma as PPO), no visibility/kill
        # reward that could pay for repeatedly losing sight of an enemy.
        reward=-.01 + .2*(.995*(0 if terminal or recovered else new_fraction)-old_fraction)
        if no_op: reward-=.05
        outcome='death' if terminal else 'recovered_quiet' if recovered else None
        if terminal: reward-=10
        if recovered: reward+=10
        truncated=not outcome and (self.steps>=self.max_steps or self.noops>=8)
        if truncated: outcome='no_turn_stall' if self.noops>=8 else 'budget_truncated'
        self.total_reward+=reward
        self.state=after
        self.history.append(frame(after,action,new_fraction-old_fraction,self.recovery.quiet))
        info=dict(turn_delta=delta,no_op=no_op,action=ACTIONS[action])
        self.audit.write(json.dumps(dict(step=self.steps,before_seq=before['seq'],
            after_seq=after.get('seq'),action=ACTIONS[action],mask=mask.tolist(),reward=reward,
            terminated=bool(terminal or recovered),truncated=bool(truncated),outcome=outcome,
            turn_delta=delta,no_op=no_op))+'\n')
        if outcome:
            info.update(outcome=outcome,case_id=self.entry['id'],damage_taken=self.damage)
            self._finish(outcome)
        return np.concatenate(self.history),reward,bool(terminal or recovered),bool(truncated),info

    def _finish(self,outcome):
        if self.finished:return
        self.audit.close()
        self.requests.close()
        self.transport.close()
        if outcome=='death':
            evidence=Path(self.state['evidence'])
            if bench.sha(evidence)!=self.state['evidence_sha256']:
                raise RuntimeError('Death evidence changed after close')
        result=dict(case_id=self.entry['id'],seed=self.entry['seed'],split=self.entry['split'],
            rng_offset=self.entry['rng_offset'],outcome=outcome,steps=self.steps,max_steps=self.max_steps,
            observed_hp_loss=self.damage,actions=dict(self.actions),reward=self.total_reward,
            final_hp=self.state.get('hp',0),quiet_turns=self.recovery.quiet,
            worker=str(self.transport.work),
            events_sha256=bench.sha(self.transport.work/'events.jsonl'),
            actions_sha256=bench.sha(self.transport.work/'actions.jsonl'))
        (self.transport.work/'episode.json').write_text(json.dumps(result,indent=2)+'\n')
        with (self.transport.workspace/'episodes.jsonl').open('a') as out:
            out.write(json.dumps(result)+'\n')
        self.finished=True

    def close(self):
        if not self.finished:
            self._finish('administrative_close')
        self.transport.close()
