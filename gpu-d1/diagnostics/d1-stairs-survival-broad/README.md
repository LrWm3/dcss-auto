# Broader verified survival practice

Follow-up to the [20-example study](../d1-stairs-survival/README.md), whose
practice improvement transferred weakly to full floors. This run keeps the
starting adapted stairs model, rewards, PPO settings, retention buffer, and
5M-decision budget. It expands the failure situations and confirmed action
corrections. It does not train on the previously audited test deaths.

## Collection and verification

Collect from the 256 training maps with ordinary enemy placements (no clumping
during collection), using the frozen source policy with sampled actions:

- Target 512 deaths, at most four per map, with half at or before physical
  turn 30 and half later. Collection is bounded at 12,582,912 decisions and
  requires at least 256 retained deaths.
- Save states zero, two, eight, 16, and 32 policy decisions before each death,
  clamped to episode start. Deduplicate repeated clamped snapshots.
- Screen every legal first action with 16 simulator RNGs, followed by the
  unchanged greedy source until exit/death/timeout. A candidate must improve
  estimated exit probability by at least 25 percentage points.
- Freeze each candidate, then confirm against the source action on 64 new,
  paired simulator RNGs. Keep it only with at least 50% exits and a 20-point
  improvement. Require at least 100 verified training examples before PPO.

Thresholds match the earlier study. They are operational filters, not formal
multiple-comparison significance tests. Changing future RNG changes movement
and combat; action changes can consume random draws differently.

Separately, collect up to 128 deaths on the 32 validation maps, capped at eight
per map and balanced by death timing. Collection is bounded at 8,388,608
decisions. Verify their alternatives with the same procedure. These states are
never used for practice resets, supervision, retention KL, or checkpoint
selection. Their maps are disjoint from training maps. This is a held-out
encounter diagnostic; the validation maps also support ordinary full-floor
checkpoint selection, so it is not a wholly untouched test set.

Compared with the earlier run, this changes example count, timing coverage,
map balance, and collection to ordinary placements. It tests a broader data
collection strategy, not the isolated causal effect of dataset size.

## Training and comparisons

Reuse the audited trainer: 384 ordinary worlds plus 128 practice worlds reset
to the expanded training-state bank with fresh future RNG. Add weight-.5
cross-entropy on confirmed first-action corrections. Ordinary training worlds
retain their existing mix of ordinary and clumped placements. The old retention
buffer and navigation anchor remain unchanged. Neither rewards nor model inputs
change; supervised examples do not reveal hidden state to the policy.

Start from the same frozen adapted stairs model as the first study, with fresh
Adam and seed 0. Checkpoints: 500,224, 1,000,448, 3,000,320, and 5,000,192 PPO
decisions. Select by mean sampled/greedy exit rate on the existing 1,024-episode
validation cohort, including the original baseline as a candidate.

After freezing selection, compare the new model, original baseline, previous
20-example model, and previous ordinary PPO control:

- 6,400 full-floor test episodes per action mode, new seed 790021.
- Up to 64 randomly selected verified training situations, 64 fresh RNGs each.
- Up to 64 randomly selected verified held-out situations, 64 fresh RNGs each.

All practice diagnostics use full greedy continuations from the evaluated model,
with no corrective action override. They report exits, deaths, timeouts, and
agreement with independently verified labels. Full-floor comparisons include
paired map-cluster bootstrap intervals. These do not cover training-seed
variation. Test layouts were used in prior studies; new placements and RNG do
not make them new layouts.

## Implementation and storage

Verification uses a fixed 2,048-world simulator buffer and evaluates the policy
only on live rows. This avoids spending most inference on finished episodes
while one episode reaches its timeout. A small compatibility check compares
outcomes with the previous full-batch implementation before training.

The native probe only reseeds RNG and reads map/placement/episode metadata.
Game mechanics are unchanged. Saved metadata verifies that collection uses
ordinary placements and that training and held-out map IDs are disjoint.

```sh
gpu-d1/.venv/bin/python -u gpu-d1/diagnostics/d1-stairs-survival-broad/run.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-stairs-survival-broad/summarize.py
```

The process holds a suite lock. Checkpoints, banks, and progress stay under
ignored `gpu-d1/learning-runs/d1-stairs-survival-broad/`, with a 4 GiB cap and
10 GiB free-space reserve. Screen chunks and PPO checkpoints support resuming.
Collection is saved as a completed bank; interrupted partial collection may
need to be restarted. SIGTERM/SIGINT requests a stop at a preparation or PPO
boundary. Do not run two instances against the same suite.

Final paired outcomes and verification reports are written compactly to
`gpu-d1/results/d1-stairs-survival-broad.json`. Preparation time, collection
decisions, PPO decisions, physical turns, and training time are recorded
separately. No checkpoint is automatically promoted over the baseline.
The summarizer writes `gpu-d1/results/d1-stairs-survival-broad-summary.json`,
including death/timeout counts, verified example coverage, and the earlier
corridor-retreat probe with fresh continuations. The probe is not used to choose
a model.

## Completed preparation

Collected 512 training deaths from 202 maps, balanced equally between early
and later deaths. Their 2,467 distinct snapshots yielded 169 independently
confirmed corrections across 97 maps: 164 moves, three attacks, and two waits.
The accepted offsets were 22 at the fatal decision, 27 at minus two, 23 at
minus eight, 42 at minus 16, and 55 at minus 32. No map supplied more than six
accepted corrections. Thus the additional examples mainly teach positioning,
including choices substantially before the fatal moment.

The separate validation collection yielded 44 verified encounters across 18
maps. These are excluded from training and checkpoint selection. Map-seed
checks and SHA256 comparisons of terrain bytes found no layout overlap among
the 256 training, 32 validation, and 100 test layouts. The active-row rollout
implementation matched all 16 outcome triples in the compatibility check.

Training completed all 5,000,192 decisions; ordinary validation selected the
3,000,320-decision checkpoint. Held-out encounter differences additionally use
a paired map-cluster bootstrap, retaining state weighting when maps contribute
different numbers of scenes. These intervals reflect map variation within the
selected challenging scenes, not uncertainty over training seeds or all possible
failure situations.

## Results

On 6,400 fresh full-floor episodes per action mode (test seed 790021):

| Model | Sampled exits / deaths / timeouts | Greedy exits / deaths / timeouts |
| --- | --- | --- |
| Original adapted model | 6269 / 131 / 0 | 6208 / 104 / 88 |
| Previous 20-example practice | 6283 / 117 / 0 | 6235 / 88 / 77 |
| Ordinary PPO control | 6267 / 133 / 0 | 6228 / 89 / 83 |
| Broader practice, selected 3M | **6310 / 90 / 0** | 6216 / 96 / 88 |

Sampled exits improve by 0.641 percentage points versus the original model
(paired map-cluster 95% interval +0.250 to +1.047), a 31.3% relative reduction
in deaths. The gain over ordinary PPO is +0.672 points (+0.313 to +1.063).
The gain over the previous 20-example model is +0.422 points, but its interval
includes zero (-0.031 to +0.891). Greedy full-floor gains are inconclusive:
+0.125 points versus the original (-0.297 to +0.531), with worse point estimates
than either trained comparison. No evidence here supports an across-the-board
improvement in both action modes.

In paired sampled episodes, broader practice turns 87 original deaths into
exits but introduces 46 deaths elsewhere. Mean physical turns remain similar:
183.35 original versus 182.15 broader. This is an improvement with regressions,
not elimination of the avoidable-death problem.

On verified encounters, each model runs its own complete greedy continuation
with 64 fresh RNGs per state and no forced corrective action:

| Model | 64 training situations: exits / 4096 | 44 held-out situations: exits / 2816 |
| --- | --- | --- |
| Original | 1796 (43.85%) | 1197 (42.51%) |
| Previous 20-example practice | 2451 (59.84%) | 1700 (60.37%) |
| Ordinary PPO control | 2243 (54.76%) | 1588 (56.39%) |
| Broader practice | **3233 (78.93%)** | **1855 (65.87%)** |

Held-out improvement versus the original is +23.37 points (map-cluster interval
+16.29 to +29.13), with 36 states improving, four worsening, and four unchanged.
The gain over ordinary PPO is +9.48 points (+1.75 to +15.96); the gain over the
20-example model is +5.50 points (-1.07 to +12.19). Thus there is evidence of
generalized encounter improvement beyond ordinary PPO, but the incremental
benefit over the smaller correction set remains uncertain.

The broader model matches all 64 sampled training labels, versus 11 of 44
held-out labels. Matching the original verified action is not required for a
successful exit: the trained continuation can solve a situation differently.

The previously audited episode-1607 corridor trap was not part of training.
Both the original and 20-example models still choose ATTACK NW there; the
broader model chooses MOVE E into the corridor with 99.875% probability.
Unforced greedy continuations on 64 fresh paired RNGs (seed 850311) exit in
24/64 cases for each earlier model and 56/64 for the broader model. This is a
specific, successful transfer of retreat behavior, not proof that all corridor
traps are solved. It was checked after checkpoint selection.

PPO took 218.2 seconds for 5,000,192 decisions and 6,296,628 physical turns;
1,250,048 decisions occurred in practice worlds. The selected checkpoint used
130.9 seconds of PPO. Collecting and verifying the training examples took
598.6 seconds; held-out preparation took another 145.5 seconds. The main
pipeline, including all comparisons, took 22.4 minutes. Additional summary and
corridor diagnostics are outside that pipeline timer.

The useful conclusion is that verified positioning practice can improve
held-out survival and sampled ordinary-floor exits. It still does not establish
that increasing example count alone caused the gain, that the gain repeats
across training seeds, or that greedy deployment improves. Rewards and policy
observations remain unchanged.
