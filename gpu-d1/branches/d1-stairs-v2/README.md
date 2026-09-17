# D1: discover stairs and descend

This is a single-floor goal-change experiment, built on the 36,000,768-decision
ordinary-floor waiting-supervised checkpoint. There is no D2, XP, loot, or
persistent progression. The existing 256 training / 32 validation / 100 test
layout split is retained. Test layouts were used in earlier tasks; they are not
newly collected maps.

## Task

- 24 ordinary enemies, no ogres, unchanged combat and regeneration.
- 15x15 wall-blocked player LOS; monster waking also requires LOS.
- 2,048 **physical turns**, including every internal REST turn.
- Three distinct synthetic stair tiles sampled each reset from reachable,
  initially unoccupied floor. Each is at least 12 Chebyshev tiles from the player
  and 8 from previously chosen stairs. Placement uses a copy of the RNG, so it
  does not consume enemy-placement or subsequent combat randomness.
- Stairs start outside LOS. Only LOS reveals them; revelation is remembered.
- Add action 18, DESCEND, masked except while standing on stairs. MOVE, ATTACK,
  WAIT, and REST retain their previous meanings and indices.
- DESCEND costs one physical turn and terminates successfully **before the next
  monster response**. Standing on or moving onto stairs alone does not exit.
  Invalid DESCEND acts as a one-turn wait, although the model's mask excludes it.
- Reward is +1 for descent minus 0.00001 per physical turn. Kills, discovery, and
  death have no separate reward. Killing the last enemy no longer ends an episode.

Thus a successful policy can leave most enemies alive. The task intentionally
provides no reason to remain for character growth.

## Observation and transfer

The old 999 inputs remain in place, including the frontier cue. Sixteen new
fields encode **remembered staircase knowledge**, not hidden exit coordinates:

| Indices | Meaning |
|---|---|
| 999 | Discovered staircase count / 3 |
| 1000 | A discovered stair is reachable through remembered floor |
| 1001–1002 | Relative position of the nearest such stair, scaled by 80 / 70 |
| 1003 | Distance along remembered floor / 150 |
| 1004–1005 | First route step as dx,dy |
| 1006–1013 | First route step as an eight-direction one-hot |
| 1014 | Standing on stairs |

The helper selects the nearest discovered reachable stair by known-floor BFS;
placement order breaks distance ties. Enemy occupancy does not alter this path,
just as with the existing frontier route cue. The action mask still prevents a
MOVE into a visible enemy. Other discovered stairs are represented by the count,
not separate global direction hints. This first study tests following an exit
goal; it does not test choosing strategically between three distant known exits.

The exact-D4 autoregressive network expands from 999 to 1,015 inputs and four to
five action types. MOVE and ATTACK still share an action-conditioned direction
head. New input weights and DESCEND weights start at zero; DESCEND bias is -4.
All old parameters transfer exactly. When the new inputs are zero and DESCEND
is masked, old action probabilities and values match the source within numeric
tolerance. D4 transforms include the new coordinate and direction fields.

## Short interface adaptation

A fixed training-only collection uses 256 worlds for 512 decisions each
(131,072 total). The source samples actions until stairs are discovered; the
observation-limited native controller then completes the encounter/navigation.
The controller descends immediately on stairs, otherwise retaining ordinary
combat/rest handling and routing to a known exit before exploring further.

Only post-discovery MOVE labels with no visible awake enemies, plus DESCEND
labels, enter the interface demonstration set. No attack, rest or wait labels
are fitted. Storage is capped at 65,536 examples. Five hundred minibatches of
512 examples fit the interface: 128 DESCEND + 384 MOVE examples per batch.
Cross-entropy is combined with weight-1 KL to the starting policy on replay
observations from the existing training-only buffer. No validation observations
or outcomes enter this fitting. The frozen adapted model is the main comparison.

## PPO continuation

One seed is evaluated at +500,224, +1,000,448, and +3,000,320 decisions, rounding
requested 500K/1M/3M checkpoints to whole 512-world steps. The expanded task starts
fresh simulator and Adam state. PPO samples every action itself. There are no
teacher overrides or auxiliary waiting labels during PPO or learned-policy eval.

PPO settings remain gamma 1, GAE lambda .95, 512 worlds x 64 steps, four epochs,
4,096 minibatch size, learning rate .0003, Adam epsilon 1e-5, value weight .25,
clip .8–1.2, gradient norm .5, and entropy coefficient zero. Timeouts are terminal
and are observed via the elapsed-turn fraction. REST rewards accumulate over all
internal turns; with gamma 1 there is no additional duration discount.

The original imitation navigation KL remains weight 1, restricted to states
with **no discovered staircase and no visible awake enemy**. Once a staircase
is known, it must not penalize the new exit goal. The existing replay buffer is
padded with zero stair features and a masked DESCEND action.

Validation uses 1,024 balanced episodes per action mode. We select a PPO endpoint
by mean sampled/greedy validation exit rate, save selection before test, then
compare it to the frozen adapted policy on 3,200 test episodes (100 maps x 32
placements), seed 950991. Paired map-cluster bootstrap intervals describe test
uncertainty, not variation between training seeds.

Metrics distinguish failure before finding stairs from failure afterwards:
exit/death/timeout rates, first discovery time, discovery-to-exit time, enemies
left alive, moves away from stairs, and sampled versus greedy action selection.
The unadapted expanded model and native controller are additional diagnostic
baselines. A high interface-adapted success rate demonstrates transfer plus
supervision; improvement from PPO must be measured against that adapted baseline.

## Checks and execution

`preflight.py` checks descent semantics for all three stairs, no automatic exit
on entry, nonterminal all-enemies-dead states, deadline termination, remembered
stair cues, and no observation leakage when unseen exits move. It also checks
4,096 paired CPU/CUDA decisions, unchanged source probabilities before discovery,
D4 covariance of the new fields, and hidden initial stairs across all map splits.

Run from the repository root:

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/d1-stairs-v2/scripts/assets.py
gpu-d1/.venv/bin/python -c "import sys; sys.path.insert(0, 'gpu-d1/branches/d1-stairs-v2/scripts'); from assets import build; build(0, True)"
gpu-d1/.venv/bin/python gpu-d1/branches/d1-stairs-v2/scripts/preflight.py
gpu-d1/.venv/bin/python gpu-d1/branches/d1-stairs-v2/scripts/run.py
```

The owned `learning-runs/d1-stairs` directory has a 4 GiB cap and 10 GiB free-space
reserve, atomic checkpoints, a single-process lock, source/library hashes, and
resume support for PPO. Source drift is rejected. It retains the adapted model,
one live resume checkpoint, and three compact endpoint checkpoints. Training
and evaluation run sequentially; logs/status live in that directory. The final
tracked report is `results/d1-stairs-v2.json`. Generated binaries, checkpoints,
and replay data remain ignored by git.

## Completed first pass

The interface demonstration collection produced 4,926 eligible observations:
4,172 MOVE and 754 DESCEND examples. Collection took 3.68 seconds and supervised
fitting took 4.43 seconds. The 500 minibatches repeatedly sampled this fixed set;
256,000 fitted examples does not mean 256,000 distinct simulator decisions.

Validation used 1,024 episodes per mode, seed 950001:

| Checkpoint | Sampled exit rate | Greedy exit rate | PPO training time |
|---|---:|---:|---:|
| Expanded source, before interface fitting | 52.44% | Not evaluated | — |
| Frozen interface-adapted source | 97.46% | 96.58% | — |
| +500,224 PPO decisions | 97.46% | 96.48% | 18.18 s |
| +1,000,448 PPO decisions | 98.54% | 96.58% | 36.43 s |
| +3,000,320 PPO decisions | 97.85% | 96.68% | 110.13 s |
| Observation-limited native controller | 97.85% | N/A | — |

The 1M PPO checkpoint won the predeclared validation selection rule. On the test
panel of 100 layouts x 32 placements, seed 950991:

| Policy / mode | Exits | Deaths | Timeouts | Exit rate | Mean turns | Enemies alive on exit |
|---|---:|---:|---:|---:|---:|---:|
| Adapted, sampled | 3,141 | 58 | 1 | **98.16%** | 188.07 | 15.70 |
| PPO 1M, sampled | 3,139 | 61 | 0 | 98.09% | 187.86 | 15.62 |
| Adapted, greedy | 3,113 | 48 | 39 | **97.28%** | 210.49 | 15.68 |
| PPO 1M, greedy | 3,106 | 51 | 43 | 97.06% | 210.32 | 15.69 |

PPO's sampled difference is -0.063 percentage points with a paired map-cluster
95% interval of [-0.563, +0.438]. Greedy difference is -0.219 points
[-0.781, +0.313]. **The short PPO continuation did not establish an improvement
over the adapted baseline.** The apparently promising 1M validation gain did
not carry through to the test comparison. There is only one training seed.

The initial stairs capability is strong. The adapted sampled policy discovers
its first stair at turn 172.73 on episodes with discovery; successful episodes
then take another 17.11 turns to descend. It leaves about two-thirds of enemies
alive. Fifty of its 58 deaths occur before discovering stairs. For greedy play,
38 of 39 timeouts also occur before discovery. This shows that most remaining
failure occurs during exploration/encounters before the exit is known.

The PPO sampled policy has 60 deaths before discovery and one afterwards,
versus 50 and eight for the adapted baseline. These are descriptive trajectory
counts, not matched-state proof of which deaths were individually avoidable.
Neither sampled policy moved away from a stair during the test episodes.

This demonstrates **transfer plus a small amount of interface supervision to a
D1 exit objective**. It does not demonstrate discovering the new interface from
sparse PPO reward alone, or a further improvement from PPO. The known-map route
helper already chooses the nearest discovered exit; autonomous choice between
multiple distant staircases was not tested.

PPO generated 3,634,312 physical turns from 3,000,320 decisions. Total measured
fitting/training time was 114.56 seconds, plus 3.68 seconds collecting interface
demonstrations. The full sequential pipeline, including validation/test, took
288.22 seconds (4.80 minutes). No jobs remain running.

Retained local checkpoints:

- `learning-runs/d1-stairs/adapted.pt`: frozen adapted baseline.
- `learning-runs/d1-stairs/checkpoints/1000448.pt`: validation-selected PPO model.
- `learning-runs/d1-stairs/checkpoints/3000320.pt`: final continuation.
- `learning-runs/d1-stairs/latest.pt`: resumable final PPO state.

The native compatibility audit additionally checked 2,048 nonterminal world
steps against the original simulator: the first 999 observations, original
18-action masks, and original 42 outcome fields matched exactly under identical
actions. This is separate from the CPU/CUDA and task-semantic preflight checks.
