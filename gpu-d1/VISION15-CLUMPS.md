# One-third clumped placement, seed 0 to 30M

2026-09-16. Test whether more concentrated encounters improve ordinary-layout
survival. Train a fresh seed-0 policy to 30M decisions, using the same initial
weights, PPO settings, 256 training layouts and 959 observations as the
seen-floor / +1 kill / +3 clear / -4 death experiment. Keep 24 normal enemies,
2048 turns, no ogres/travel, +0.002 first-seen floor reward, -0.001 turn cost,
15x15 wall-blocked vision and LOS-gated waking.

Select clumped placement independently with probability 1/3 at every reset.
This is a fraction of episodes, not necessarily a fraction of training turns.
Ordinary placement remains unchanged in the other episodes. The original
regular-enemy spawn rule excludes the player's tile, without a minimum distance.
Preserve that rule. No placement label is exposed to the model.

For a clumped episode, first generate normal positions, stats and energy, then
relocate the 24 enemies into eight triples using a separate copy of the RNG.
Each anchor is uniformly selected among currently empty floor tiles with two
eligible neighbors. Select two distinct neighboring floor tiles uniformly
without replacement, excluding the player and previously placed enemies.
Different triples may touch. Stats, energy, sleep and gameplay RNG are preserved;
initial vision/discovery is calculated after relocation. Clumping does not make
enemies wake as a group: normal individual LOS/wake rules apply.

## Validation and evaluation

Before training, check 4,096 initial worlds across all 256 training layouts for
each mode (ordinary, one-third mix, all clumped): valid distinct tiles, player
exclusion, triple geometry, original HP/energy and sleeping state. Check the mix
frequency is between 30% and 37%. Check ordinary-mode observations, masks and
step outputs exactly match the previous simulator for 64 worlds x 128 steps.
The added internal placement flag changes state size, so compare behavior rather
than raw state bytes against the old simulator.

Training checkpoints evaluate on ordinary validation placement. After training,
evaluate the existing ordinary-trained 30M policy and the mixed-trained 30M policy
on both ordinary and fully clumped placement: 1,024 sampled episodes per cell,
32 held-out validation layouts x 32 episodes, seed 900000. Test layouts untouched.
Retain separate labels for each training/evaluation combination.

Report clears/deaths/timeouts, mean turns/kills, single/multi-enemy contact,
fatal crowding, walls and retreat opportunities. Reuse the read-only wall/death
probe, with original fatal-action replay and 128-step state/observation/output
parity checks. Ordinary evaluation must reproduce each stored training result.
Clumped evaluation is a new distribution, so it has no prior outcome reference.
Geometry and one-turn survival do not establish eventual escape.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-clumps-v1/scripts/run_experiment.py
```

Artifacts: `results/vision15-clumps-preflight.json`,
`results/vision15-clumps-30m.json`, `results/vision15-clumps-evaluation.json`.
Training time excludes evaluation/setup/I/O; the launcher records total wall time.
Checkpoints are bounded to a 2 GiB suite with a 5 GiB free-space reserve. Existing
ignore rules cover builds, checkpoints and logs. This is a one-seed exploratory
screen; better ordinary validation is the main evidence for useful transfer.
