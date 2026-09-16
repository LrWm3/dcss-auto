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
