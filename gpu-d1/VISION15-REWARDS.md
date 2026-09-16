# Reward incentives and aggressive combat: 10M screen

2026-09-15. Seed 0, train and validate with 2048 physical turns, 24 ordinary
enemies, no ogres, no travel, 15x15 wall-blocked vision and LOS-gated waking.
Same 256 training maps, 32 validation maps x 32 episodes, PPO settings, clock,
exploration bonus (+0.002) and turn cost (-0.001) as the completed fixed-2048
baseline. Test maps untouched. Nine checkpoints from initialization to 10M.

| Variant | Kill | Clear bonus | Death |
|---|---:|---:|---:|
| Existing baseline | +1 | +3 | -1 |
| death4 | +1 | +3 | -4 |
| completion | +0.25 | +21 | -1 |

Reuse the completed baseline at `learning-runs/vision15-no-travel-train2048-10m`.
Train both new policies from initialization, not from baseline weights. The
completion variant retains total undiscounted kill-plus-clear reward of +27.
It changes timing, discounting and learning incentives: it is not equivalent to
rescaling the original rewards. No comparison of raw shaped return across
variants should be interpreted as a comparison of ability.

Implementation isolates changes in `branches/vision15-rewards-v1`. Native
compile-time kill and clear reward constants replace hardcoded values, retaining
original defaults. Death reward uses the existing parameter. Library keys and
manifest jobs include all reward constants. Old experiment source is unchanged.

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-rewards-v1/scripts/run_screen.py
gpu-d1/.venv/bin/python gpu-d1/branches/vision15-rewards-v1/scripts/diagnose_rewards.py
```

The screen verifies identical corpus and non-reward jobs against the baseline,
equal initial-policy outcome metrics, and identical checkpoints. After training,
64 paired episodes per variant use the same baseline policy actions in original
and modified simulators. Full state, observations, masks and non-reward outputs
must match exactly, and each reward must equal the baseline plus the intended
kill/clear/death differences. Coverage must include kills, clears and deaths.

Evaluate clears, deaths, timeouts, kills and episode lengths. Apply existing
death diagnostics to the final policies; inference uses the original simulator
reward because reward is not a policy input and no learning occurs. Full-episode
outcomes must match each variant's training-run validation. See
`diagnostics/deaths/README.md` for definitions and counterfactual limitations.
The diagnostic extension is unchanged. A single training seed is exploratory.

Bounded retention: latest/best plus small milestone checkpoints, 2 GiB suite cap,
5 GiB free-space reserve. Existing ignore rules exclude generated weights,
libraries and logs. Training seconds exclude compilation, evaluation and I/O.
