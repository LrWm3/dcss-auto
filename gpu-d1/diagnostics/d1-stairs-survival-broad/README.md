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
corridor-retreat observation probe. The probe is not used to choose a model.
