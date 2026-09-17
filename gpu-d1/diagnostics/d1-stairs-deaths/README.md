# Are the D1 stairs deaths avoidable?

Some are demonstrably avoidable tactical errors. All 58 sampled deaths have a
successful alternative trajectory under their original simulator RNG state,
when we intervene early enough. This does **not** establish that a deployable
policy could reliably prevent all 58 deaths: hindsight search finds favorable
trajectories, and many late rescues do not survive changes in future randomness.

This is an evaluation-only audit of the frozen **adapted** stairs checkpoint,
not its PPO continuation. No training, reward, or policy default changed.
See the [D1 task](../../branches/d1-stairs-v2/README.md),
[per-death results and traces](../../results/d1-stairs-deaths.json), and
[generic early-switch results](../../results/d1-stairs-deaths-early.json).

## Cohort and replay verification

The original sampled test used 3,200 episodes: 100 layouts x 32 placements,
seed 950991. It produced 3,141 exits, 58 deaths, and one timeout. This audit
examines all 58 deaths, excluding the timeout and successful episodes.

We regenerated all 3,200 original outcomes exactly, then saved five states per
death, including complete native state, simulator RNG, observations, and masks.
Replaying the recorded original actions reproduced all 290 deaths and all 45
terminal metrics exactly. Snapshot timings are:

- Immediately before the fatal policy decision.
- Eight and 32 policy decisions earlier, clamped to the episode start.
- The most recent transition from no visible enemy to any visible enemy,
  with episode start as fallback (called encounter start below).
- Episode start.

Policy decisions are not physical turns: REST can consume multiple turns.
The original 2,048-physical-turn deadline remains in force after restoration.

## Legal-action search under the original RNG

At each snapshot we tried every legal first action, then continued to a full
exit, death, or timeout using each of three controllers:

1. **Base:** the current adapted stairs model, greedy.
2. **Teacher:** the native observation-limited stairs/combat controller.
3. **Tactical switch:** the older balanced tactical model, greedy, whenever an
   awake enemy is visible and the player is not standing on stairs; otherwise
   the current stairs model, greedy. The old model receives zero-weight new
   stair inputs and cannot select DESCEND in its combat branch.

All controllers use the ordinary observations and legal-action masks. The
offline choice between successful alternatives uses hindsight.

| Intervention point | Any tested first action + continuation exits | Base alone exits | Teacher alone exits | Tactical switch alone exits |
|---|---:|---:|---:|---:|
| Fatal decision | 30/58 | 2/58 | 3/58 | 1/58 |
| Eight decisions earlier | 46/58 | 14/58 | 16/58 | 23/58 |
| 32 decisions earlier, or start | 58/58 | 30/58 | 32/58 | 42/58 |
| Encounter start | 58/58 | 31/58 | 37/58 | 48/58 |
| Episode start | 58/58 | 37/58 | 39/58 | 50/58 |

The three “alone” columns do not select an alternative first action: each
controller chooses its own first action. The first column takes the union of
all legal first actions and all three continuations.

Four fatal states have **no legal action that survives that decision's
execution under the original RNG**. Earlier alternatives still exit. These
states demonstrate why the final action alone cannot explain every death;
they do not demonstrate an unavoidable episode.

## Fresh randomness: how reliable are the rescues?

For each death we selected the latest successful intervention under the
original RNG, preferring base, then teacher, then tactical continuation. Within
that choice we preferred exit HP, then fewer turns. Selections were saved before
testing 64 new simulator RNG states per saved scene, paired between controllers.
Positions, HP, energy, regeneration, knowledge, and elapsed time remain fixed.
Both combat and monster movement randomness can change.

At these mostly late intervention states:

- Base greedy exit rate: **42.40%**.
- Selected alternative exit rate: **48.25%**.
- **Six cases** meet the predeclared descriptive threshold of at least 75%
  exits and at least a 20-percentage-point improvement over base greedy.

That threshold is a diagnostic screen, not a multiple-comparison significance
test or an estimate of the total number of avoidable deaths. Failure to meet
it does not establish unavoidability, especially for already damaged states.

Separately, we tested the same fixed tactical switch from encounter start for
all 58 cases, without selecting the first action by its outcome. Across 64
fresh RNGs per case:

| Continuation | Exit rate |
|---|---:|
| Base greedy | 74.84% |
| Tactical switch | 77.86% |

The switch improved 29 cases, worsened 19, and tied on 10; five met the same
strong-rescue threshold. This is mixed evidence, not a universal controller fix.
Both comparisons use greedy continuations, whereas the original deaths came
from a sampled policy. These are rates conditional on selected death states,
**not overall-floor performance**. Do not apply them to all 3,200 episodes.

## Concrete avoidable retreat error

Episode 1607, case 26, reaches this corridor mouth at 4 HP with three adjacent
awake foes (`g`), the player (`@`), and walls (`#`):

```text
g#####
g@....
g#####
```

The original sampled action and the current greedy choice both attack NW.
Under the original RNG that attack dies. Force **one MOVE E**, then give the
unchanged greedy model control: it fights one adjacent foe at a time, rests,
finds stairs, and exits at turn 332 with 18 HP.

Across 64 fresh simulator RNGs, base greedy exits **26/64 (40.6%)**; the single
east step followed by the same model exits **50/64 (78.1%)**. This is a concrete
risk-reducing maneuver, not guaranteed survival, and does not require a
different continuation controller. Full geometry and traces are in the JSON.

Episode 1608 supplies a second example: the original sampled trajectory
oscillates north/south near defensive geometry. At the selected earlier state,
base greedy exits 0/64; a forced WAIT followed by the native controller exits
54/64. That intervention changes the subsequent controller too, so this is
not evidence that a single WAIT by itself fixes the episode.

## What characterizes these deaths?

- 34/58 occur within the first 30 physical turns; median death turn is 26.
- At the fatal decision, adjacent foe counts are: one in 11 cases, two in 18,
  three in 26, and four in three. Thus **47/58 face multiple adjacent foes**.
- Fatal actions: 45 ATTACK, 11 WAIT, two MOVE. These counts describe the final
  decision; they do not assign blame to that action type.
- 50 deaths occur before discovering stairs, eight after discovery.

The evidence supports improving early encounter positioning and crowd
handling. It does not show that stairs navigation causes the deaths, that
retreat always helps, or that these death states are representative of normal
encounters. We have not compared their initial encounter density to survivors.

## Scope and limitations

Exact saved RNG state preserves simulator reproducibility, not event-by-event
luck: different actions can consume random draws differently. Finding an exit
establishes existence under the simulator, not an observation-only way to
choose it reliably. Failing this finite search would not prove impossibility.
No exhaustive multi-step planning or estimate of optimal survival probability
was attempted.

These are diagnostic uses of the prior test failures. If their states are later
used for training or controller tuning, they become development data; evaluate
any claimed improvement on untouched episodes as well as the full regression
cohort, including the previously successful cases.

## Reproduce

From the repository root, with the existing checkpoints and GPU environment:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-stairs-deaths/run.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-stairs-deaths/early.py
```

Run these sequentially. `run.py` records both checkpoint SHA-256 hashes in its
manifest and checks them on resume. `early.py` uses its snapshots and screen;
keep the checkpoints unchanged between commands. Native compilation uses
the unchanged D1 stairs simulator plus the diagnostic-only RNG reset in
`probe.cu`. Large artifacts are ignored under
`gpu-d1/learning-runs/d1-stairs-deaths/`; the main store has a 4 GiB cap and
10 GiB free-space reserve, and the early comparison has a 2 GiB cap. JSON
results and scripts are tracked. The JSON `wall_seconds` measures its producing
invocation, which may reuse cached stages; it is not total audit compute time.
