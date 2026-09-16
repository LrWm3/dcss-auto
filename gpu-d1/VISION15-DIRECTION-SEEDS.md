# Do tactical direction biases depend on the training seed?

Queue behind the complete D4 training/evaluation pipeline. Train four fresh
unaugmented policies: ordinary and one-third-clumped placement, each at seeds
1 and 2, to 30,015,488 decisions. Together with historical seed 0, this gives
three seeds per placement regime. All simulator, model, PPO, corpus, reward,
vision and turn-limit settings match the original clumps experiment.

Within each seed, ordinary/clumped initial model weights must match; both seeds'
initializations must differ from seed 0. Native sources must match exactly.
Training validation uses the same 32 held-out maps x 32 episodes, ordinary
placement, and evaluation seed 900000. Test layouts remain untouched.

For each trained pair rerun the same full hallway, six-enemy hallway, two-step
diagonal pocket, four-/six-step pocket, rotated/mirrored forced-route, and static
single-enemy action tests. Preserve every roster/HP/orientation condition, natural
and forced-retreat arms, and 512 combat seeds per condition. Scripted controls
must exactly reproduce historical results. Prefix results `seed1-noaug-` and
`seed2-noaug-`; no historical results are overwritten.

The primary comparison is whether high-wait directions differ across training
seeds, and whether each seed shows a large within-policy orientation gap. Also
compare natural retreat success, forced-route defense, and ordinary clear rates.
Do not treat mirrored/rotated cases sharing combat seeds as independent repeats,
or three training seeds as a precise estimate of the population of trained agents.

Run `gpu-d1/.venv/bin/python gpu-d1/branches/vision15-direction-seeds-v1/scripts/run_experiment.py`.
The launcher waits for the currently recorded D4 process to exit and requires its
completion marker. If that pipeline fails, it stops visibly rather than competing
for the GPU or silently skipping prerequisite work. It can then be relaunched.

Suite: `learning-runs/vision15-direction-seeds-30m`; 2 GiB checkpoint budget,
5 GiB free-space reserve. Training times and validation curves are recorded per
model. Full pipeline report: `results/vision15-direction-seeds-run.json`.

## Completed results

All four additional policies reached 30,015,488 decisions and completed every
scheduled diagnostic. Native-source, paired-initialization and scripted-control
checks passed. Pipeline elapsed after queue: 1810.61 seconds (30.18 minutes).
Ordinary training seeds 1/2 took 221.16/220.35 seconds; clumped 272.04/269.12.
Ordinary validation clears: ordinary seeds 1/2 both 78.03%; clumped 78.52%/75.39%.

Directional findings depend on the diagnostic. In the static full-health kind-3
single-enemy test at player HP 12, worst wait probabilities/orientations:

| Model | Seed 0 | Seed 1 | Seed 2 |
|---|---:|---:|---:|
| Ordinary | NW 39.1% | NW 5.8% | SE 78.1% |
| Clumped | NE 40.3% | SW 36.9% | SE 56.9% |

But in six-enemy, six-step-pocket rollouts after forcing the full route, the
highest contact-wait orientation remains NW for ordinary and NE for clumped in
all three seeds. The strongest-contact-wait rates are:

| Model | Seed 0 | Seed 1 | Seed 2 |
|---|---:|---:|---:|
| Ordinary, NW pocket | 63.3% | 91.8% | 32.6% |
| Clumped, NE pocket | 84.5% | 68.3% | 49.8% |

Thus neither 'entirely random directions by seed' nor a single static probe
summarizes the phenomenon. Severity and static action preferences vary strongly;
the multi-enemy rollout has a repeated orientation pattern, potentially involving
learned behavior, observation conventions and simulator directional tiebreaks.
These tests do not isolate the cause.

Tough-roster/player-12-HP natural clear rates:

| Test/model | Seed 0 | Seed 1 | Seed 2 |
|---|---:|---:|---:|
| Three-step hallway, ordinary | 7.42% | 24.12% | 22.56% |
| Three-step hallway, clumped | 51.81% | 51.56% | 62.06% |
| Six-step pocket, ordinary | 5.96% | 2.29% | 25.98% |
| Six-step pocket, clumped | 19.29% | 16.65% | 37.16% |

Clump training's hallway advantage appears in all three paired seeds. Pocket
performance varies substantially even without augmentation; seed-0 augmentation
changes should therefore not be taken as a robust general effect. Full-route
six-step pocket clear rates ordinary: 63.57/43.21/78.03%; clumped: 63.48/67.09/69.58%.
