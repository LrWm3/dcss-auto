"""Small fixed encounter intentions; only player-visible geometry is available."""
from experiment import DIRECTIONS
from train_encounters import actions, enemies

POLICIES=('baseline','hold','rage_hold','retreat','retreat_fight')


class Tactic:
    def __init__(self,policy):
        if policy not in POLICIES:raise ValueError(policy)
        self.policy=policy;self.heading=None;self.committed=False

    def __call__(self,state):
        allowed=actions(state);es=enemies(state)
        if self.policy=='baseline':return 'baseline'
        # Delegate status recovery and emergency resources to the established RC.
        if state.get('confused') or state.get('poisoned') or state.get('on_fire'):
            return 'baseline'
        if not es:return 'wait' if state.get('safe') else 'baseline'
        if state.get('berserk') or self.committed:
            return 'melee' if 'melee' in allowed else 'baseline'
        if self.policy in ('hold','rage_hold'):
            if self.policy=='rage_hold' and 'berserk' in allowed:
                self.committed=True;return 'berserk'
            if state['hp']/state['max_hp']<.35:return 'baseline'
            return 'melee' if 'melee' in allowed else 'wait'
        # A visible-terrain retreat, NOT a promise that this leads to stairs or
        # explored safety. Prefer greater closest-enemy distance, then weighted
        # distance from threats, then continue the previous heading.
        def score(x,y):
            ds=[max(abs(e['x']-x),abs(e['y']-y)) for e in es]
            return min(ds),sum((1+e['threat'])*d for e,d in zip(es,ds))
        moves=[a for a in DIRECTIONS if a in allowed]
        if moves:
            best=max(moves,key=lambda a:(*score(*DIRECTIONS[a]),a==self.heading))
            if score(*DIRECTIONS[best])>score(0,0):
                self.heading=best;return best
        if self.policy=='retreat_fight' and 'berserk' in allowed:
            self.committed=True;return 'berserk'
        if 'melee' in allowed:return 'melee'
        return 'baseline'
