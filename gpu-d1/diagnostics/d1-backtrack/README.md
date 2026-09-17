# Backtracking past an unresolved dangerous frontier

Completed2026-09-17. Frozen-policy evaluation only; no new training or production
changes. The full screen took88.0 seconds including fixture generation, native
build, preflight and18,432 evaluation episodes.

## Geometry and observation history

An L-shaped corridor is rotated/reflected in all eight square symmetries. The
player actually walks from the junction to the evaluation start, revealing the
corridor through the production simulator. Backtracking distances are4/8/16/24.
The following is conceptual; corridor lengths are not to scale:

```text
stairs (three exits, all initially unseen)
  |
unseen continuation
  |
known branch, seen from the junction
  |
junction ----- already-walked corridor ----- @ ------ sleeper --- unseen dead end
```

The sleeper starts seven tiles ahead, visible but outside its six-tile wake
range. The nearest frontier points toward it. The dead-end wall is14 tiles
ahead and initially unseen. Three stairs lie12/16/20 tiles along the other
branch; all are unknown at the evaluation start. The player must backtrack and
then advance into that branch before discovering stairs and obtaining a stair
cue. Eight-direction corner cutting remains the normal simulator rule, so a
junction turn may save one step relative to the drawn orthogonal route.

For each geometry use no enemy, a weak sleeper (HP6, damage cap4), or a strong
sleeper (HP24, damage cap20). Player stats are full18HP and damage cap4.
The2048 physical-turn deadline includes the preceding4/8/16/24-turn walk.
No death is needed to solve any scenario. Oracle preflight followed actual
simulator transitions in192 checks and exited with no wake, damage, or kills.

LOS uses the same native ray fixture as the ordinary corpus. Tiny disconnected
corner rooms support the existing terminal autoreset's spawn requirements;
they are invisible/unreachable from the test corridor. They contain no active
test enemies or exits. The policy receives only its normal observations.

## Main results

All three checkpoints solved **100% of no-enemy and weak-enemy cases**, both
sampled and greedy, across every distance and orientation. Weak enemies were
killed; the empty/cleared dead end was then explored and the policy backtracked
successfully to find the stairs.

With the strong enemy, **all greedy evaluations timed out**, with no deaths,
no enemy wake-ups, and no WAIT actions. This occurred in all eight orientations
at all four distances, for the starting5M, ordinary-continuation6M and
practice-continuation6M checkpoints. The failure is a movement loop, not waiting.

Strong-enemy sampled exit percentages,256 episodes per cell (eight orientations
x32 random futures):

| Backtrack | Starting5M | Ordinary continuation6M | Bypass practice6M |
| --- | ---: | ---: | ---: |
|4 tiles|87.11%|97.27%|98.44%|
|8 tiles|13.67%|1.56%|1.56%|
|16 tiles|7.03%|0%|0.78%|
|24 tiles|7.03%|0.39%|0.78%|

Successful escape without killing the strong enemy, as a percentage of all
sampled trials:

| Backtrack | Starting5M | Ordinary continuation6M | Bypass practice6M |
| --- | ---: | ---: | ---: |
|4 tiles|83.59%|97.27%|98.44%|
|8 tiles|7.81%|1.17%|0.78%|
|16 tiles|2.73%|0%|0.39%|
|24 tiles|0.39%|0.39%|0%|

Thus some longer-distance source successes come from surviving a fight, not
from solving the intended avoidance/backtracking task. At24 tiles, the source
had18 exits but only one left the enemy alive; practice had two exits and both
killed it. The small practice advantage at four tiles is not isolated from the
ordinary continuation, which improves similarly.

Orientation does not rescue greedy behavior. Sampled variation exists, but
32 futures per orientation and one base topology do not establish a systematic
directional bias. These are controlled capability probes, not estimates of
ordinary-floor performance or independent training-seed replications.

## Observed mechanism and information loss

Representative48-decision greedy traces, in the canonical orientation for all
four distances, repeat:

1. At the starting tile, strong sleeper visible: move backward.
2. One tile back, sleeper outside the15x15 view: follow frontier forward.
3. Return to the starting tile; repeat.

The frontier continues pointing forward. Later movements can vary with the
elapsed-time input, but none of the greedy episodes completes the backtrack.
The complete raw measurements retain maximum backtracking distance, waiting,
junction arrival, discovery of the other branch, stair discovery, and outcomes.

A separate paired-state check performs the same one-step backward move in the
no-enemy and strong-enemy scenarios. **The entire observation and legal-action
mask are byte-identical in every one of the32 map pairs.** The unseen enemy's
last-known presence is not represented. The policy is feed-forward, so it has
no recurrent state with which to distinguish those histories.

This supports a specific limitation of the current setup: local threat
avoidance does not persist after the threat leaves vision, while the single
frontier cue still points toward it. It does not prove arbitrary backtracking
is impossible to learn. The controls demonstrate backtracking once the near
frontier is exhausted, and short sampled escapes do succeed. Nor does this
screen isolate whether remembered threats, persistent navigation goals,
alternative frontier information, or different training would best fix it.

## Reproduction and artifacts

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-backtrack/run.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-backtrack/trace.py
```

Raw fixtures/native library/results stay under ignored
`learning-runs/d1-backtrack/`. Tracked `results/d1-backtrack.json` retains all
orientation-level outcomes, checkpoint hashes, representative traces, and the
paired observation check. All scenarios are independent of training data;
checkpoint choice is fixed, with no selection based on these results.

## Variant: stairs already known

Completed 2026-09-17, using `run.py --known-stairs`. No training. Same
32 geometries, three enemy conditions, three checkpoints, greedy/sampled modes,
and 32 futures per cell: 18,432 episodes, plus 192 successful oracle checks.
Runtime including maps and native compilation: **32.75 seconds**.

Instead of starting its history at the junction, the player starts on the first
stair and walks 12 squares to the junction, then follows the original corridor
history. Two stairs and a connected return route are therefore known through
ordinary observation updates. The third stair and dangerous dead-end wall remain
unknown. Initial HP, enemy state, and evaluation-start position are unchanged.
The additional 12 history turns count toward the same 2048-turn deadline.
Assertions check the actual observed frontier still points toward the enemy,
while the existing stair guide points in the other direction.

**Every evaluation exited; no deaths or timeouts.** All exits left enemies alive;
no enemy woke. For strong-enemy cases:

| Backtracking distance | Unknown stairs, greedy (all models) | Known stairs, greedy and sampled (all models) | Greedy turns after evaluation starts |
| --- | ---: | ---: | ---: |
| 4 | 0% | 100% | 16 |
| 8 | 0% | 100% | 20 |
| 16 | 0% | 100% | 28 |
| 24 | 0% | 100% | 36 |

Each model/mode/distance cell contains 256 episodes across eight orientations.
Greedy repetitions have no combat randomness on these safe paths and should not
be interpreted as 256 independent behavioral tests. Sampled strong-enemy means
are within 0.051 turns of the corresponding greedy values. Greedy never waits.
No strong-enemy episode enters the dangerous branch; the control checkpoint
briefly does so in one sampled **no-enemy** episode, which also exits.

This sharpens the earlier conclusion: these policies can sustain long return
journeys when the existing stair guide provides a destination, even with a
conflicting frontier cue and a visible dangerous enemy. Failure with unknown
stairs is more specifically about selecting/persisting toward an alternative
exploration destination. This does not demonstrate general planning or prove
which change would solve it. The intervention includes known terrain, stair
knowledge, its existing route guide, and 12 extra elapsed turns; it does not
isolate their individual causal contributions. These are the same synthetic
corridor family and checkpoints, not a new ordinary-floor success estimate.

Tracked outcomes: `results/d1-backtrack-known-stairs.json`. Generated artifacts
are isolated under ignored `learning-runs/d1-backtrack-known-stairs/`; the
unknown-stairs results and default runner behavior are preserved. A setup smoke
check also exercises the unknown-stairs path using the updated native library.
