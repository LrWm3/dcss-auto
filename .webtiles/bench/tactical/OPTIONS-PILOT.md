# Encounter-level option selection

```sh
/usr/bin/python3 .webtiles/bench/tactical/train_options.py \
  .webtiles/bench/tactical/options-pilot-v1.json \
  .webtiles/bench/tactical/artifacts/options-pilot-v1
```

This first experiment makes **one decision per encounter**. It chooses an
existing stateful tactic: retreat, hold position and fight, berserk-and-hold,
or RC control. The selected tactic persists until the shared harness endpoint;
heading and commitment are not reset every turn. The existing hazard shield
still overrides individual actions. These tactics can themselves delegate
emergencies to the RC. Neither safety nor successful escape is guaranteed.

This is a full-feedback **contextual bandit** (one-step episodic RL), not a
multi-step hierarchical RL agent. Every option is tried from each of five
training checkpoints, with independent engine resets. Linear values are fit
to the 20 observed bounded outcome rewards using normalized squared-error
updates. All outcomes, including deaths, train the values. There is no
bootstrapping or low-level movement learning. Feature vectors contain only
the existing player-visible features and encounter-entry memory; case IDs
and seeds are retained for audit but never used as model inputs.

The frozen model selects the maximum-valued option; ties prefer retreat,
then hold, rage_hold, baseline. A zero model therefore defaults to retreat.
Training budget is defined by all four options per training case, not the
legacy `episodes` setting retained for shared config validation. `fit_epochs`
controls regression passes; legacy alpha/gamma/epsilon are unused here.

After fitting, compare selector, fixed retreat, and the exact hash-pinned
imitation model from rl-replay-pilot-v1 on five training and six validation
checkpoints (53 game trials overall). The loader enforces seed partitions;
validation outcomes do not enter fitting. Reference training cases, split,
engine, adapter and continuation settings are checked before launch.
One validation seed and single deterministic replays remain weak evidence
of generalization. Reserved test remains excluded; no automatic deployment.

The shared bounded follow-up credit remains unchanged: death including RC
continuation is -1, alive floor change or recovered continuation endpoint +1,
other budget/stall endpoints zero. This is not floor clearance. Handoff occurs
at the existing proxy-recovery endpoint; **handoff timing is not learned yet**.
Keeping this fixed isolates option selection from another controller change.
See REPLAY-PILOT.md for the reward limitations and legacy reward-file warning.

`training-outcomes.json` stores the encounter-level training transitions;
`option-transition.json` records entry features and selected option per trial.
`audited-result.json` records delayed outcomes and shield override counts.
`model.json`, source/checkpoint provenance and summary preserve the experiment.
