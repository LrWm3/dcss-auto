"""Require a material predicted advantage before committing to rage_hold.

Scores are fitted values, not calibrated probabilities or uncertainty bounds.
The rule affects option selection only; delegated RC may still choose berserk.
"""
import math
from train_encounters import features, value
from train_options import OPTIONS, OptionController


def select_option(model,f,margin=.05):
    if not math.isfinite(margin) or margin<0: raise ValueError('Invalid berserk margin')
    scores={a:value(model,a,f) for a in OPTIONS}
    if not all(math.isfinite(v) for v in scores.values()): raise ValueError('Nonfinite option score')
    raw=max(OPTIONS,key=scores.get)
    alternative=max((a for a in OPTIONS if a!='rage_hold'),key=scores.get)
    chosen=raw
    if raw=='rage_hold' and scores[raw]-scores[alternative]<=margin:
        chosen=alternative
    return dict(option=chosen,raw_option=raw,scores=scores,
                margin=margin,guard_applied=chosen!=raw)


class ConservativeController(OptionController):
    def __init__(self,model,margin=.05):
        super().__init__(model)
        self.margin=margin;self.selection=None

    def __call__(self,state,memory,allowed):
        if self.tactic is None:
            self.selection=select_option(self.model,features(state,memory),self.margin)
            self.fixed=self.selection['option']
        return super().__call__(state,memory,allowed)
