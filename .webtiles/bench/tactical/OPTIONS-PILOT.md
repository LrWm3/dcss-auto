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

## Collecting useful option contrasts

`screen_training_options.py INDEX OUTPUT --jobs 4` accepts a training-only
verified index. It checks checkpoint/engine hashes and seed assignments before
launch, tries retreat on every eligible case, then tests hold, rage_hold and RC
control only where retreat's bounded outcome is nonpositive. Its summary lists
successful alternatives. No model is fit and no validation/test games are run.
The collected option transitions can support later training; untested options
are missing observations, not failures. This selective screen is deliberately
biased toward retreat failures and must not be treated as a full option matrix
or an unbiased estimate of other tactics' overall success rates.

## Expanded full-matrix experiment

`train_options_expanded.py options-expanded-v1.json OUTPUT` uses the original
five training checkpoints plus 22 newly verified ones. It reuses 54 pinned
option labels (20 original, 34 from selective screening), runs the 54 missing
trials, and checks that all 27 x 4 outcomes are present before fitting once.
Cached label bytes, manifest/results, checkpoint identity, sources, and bounded
task settings are validated; case paths map collection-local IDs to namespaced
dataset IDs. Only training cases can supply fitting labels.

The fit algorithm, 1000 epochs, features, four tactics and reward are unchanged
from the first option pilot. No validation-driven selection or tuning is done.
The frozen selector is replayed on all 27 training cases. Validation runs the
selector, fixed retreat, RC and the exact old imitation model on six checkpoints
from its separate seed. Imitation is a frozen smaller-data reference, not an
equally trained model. Reserved test is not run. Expected new game trials:105.

Reports distinguish positive bounded outcomes, deaths, neutral endpoints,
floor changes, and descent within the same branch. A recovered RC budget
endpoint is positive but does not count as floor progress. Ascent counts only
as a floor change; changing branches is not labeled deeper-same-branch. No
floor-change metric implies clearance. These metrics do not change rewards.

Artifacts preserve the full training matrix, source hashes, cached-label
provenance, frozen model and all new trial results. Old corpora/models remain
unchanged; this run does not deploy anything.

## Conservative berserk selection

`evaluate_conservative_options.py options-conservative-v1.json OUTPUT` evaluates
the unchanged expanded model with one new selection rule: `rage_hold` must beat
the best non-rage option by **more than 0.05** predicted reward. Otherwise use
that alternative. The margin is a training-informed heuristic on fitted values,
not a calibrated uncertainty estimate. No monster identities, floors, case IDs,
or validation outcomes enter the rule. Delegated RC can still decide to berserk.

The original selector and model remain unchanged. Training-label inspection
identifies three changed decisions: D7 to retreat (repairs known failure), one
already-successful case to RC, and the all-options-fail gnoll case to retreat.
Eustachio's larger berserk advantage and Terence's RC choice remain unchanged.
Margin is fixed before validation, no weight fitting is performed, and the
runner replays all27training cases plus24frozen validation comparisons.
Hash-pinned source model/matrix, selection scores/reasons and progress metrics
are saved. Test seeds and production RC remain untouched.
