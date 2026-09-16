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
equal initial-policy outcome metrics, and matching checkpoint milestones. After training,
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

## Completed results

Both new runs reached 10,027,008 decisions. Sampled policy, 1,024 validation
episodes per checkpoint. All columns use a 2048-turn evaluation deadline.

| Training decisions | Baseline clear | Death -4 clear | Completion-focused clear |
|---|---:|---:|---:|
| 0 | 0.00% | 0.00% | 0.00% |
| 131,072 | 0.00% | 0.00% | 0.00% |
| 327,680 | 0.00% | 0.00% | 0.00% |
| 1,015,808 | 0.00% | 0.00% | 0.00% |
| 2,031,616 | 40.72% | 41.99% | 40.82% |
| 3,014,656 | 46.09% | 51.95% | 35.94% |
| 5,013,504 | 54.88% | 57.32% | 37.40% |
| 7,503,872 | 58.20% | 62.60% | 37.11% |
| 10,027,008 | 61.52% | 67.29% | 39.65% |

Final checkpoint:

| Rewards | Clear | Death | Timeout | Mean turns | Mean kills | Training seconds |
|---|---:|---:|---:|---:|---:|---:|
| Baseline | 61.52% | 37.40% | 1.07% | 473.4 | 18.35 | 69.55 |
| Death -4 | 67.29% | 30.76% | 1.95% | 533.2 | 19.51 | 69.84 |
| Kill +0.25, clear +21 | 39.65% | 59.47% | 0.88% | 515.2 | 14.09 | 70.52 |

The stronger death penalty increased clear rate by 5.76 percentage points and
reduced death rate by 6.64 points in this seed. Timeouts increased by 0.88 points.
The completion-focused alternative reduced clears by 21.88 points and increased
deaths by 22.07 points; it did not simply become cautious and time out.

The reward function affects these outcomes even with a long training deadline.
This supports investigating survival incentives, but does not establish that
aggression alone explains the difference. Reducing immediate kill feedback and
moving reward to a distant clear may make learning harder; that is a hypothesis,
not isolated by this experiment. Gamma, reward timing, reward variance and value
learning remain coupled. No multi-seed superiority claim is warranted.

Both reward implementations passed paired 64-episode validation with identical
state transitions, observations, masks and non-reward outputs. Each covered
1,202 kills, 39 clears and 23 deaths. Reward changes matched the explicit formula
on every active step. Initial-policy outcomes and corpus hashes also match the
baseline. Runtime training was about 70 seconds per new variant; this excludes
compilation, checkpoint I/O and evaluations. The baseline was reused.

Artifact: `results/vision15-rewards-10m.json` includes complete sampled/greedy
curves, per-map metrics, timing, hashes and verification counts.

## Combat diagnostics

The final policies reproduce their validation outcomes exactly in the unchanged
diagnostic simulator. Full-state parity and fatal-action replay checks pass.

| Measure | Baseline | Death -4 | Completion-focused |
|---|---:|---:|---:|
| Mean turn of death | 177.9 | 208.7 | 234.0 |
| Fatal action was attack | 86.7% | 82.2% | 69.5% |
| Deaths with 2+ adjacent enemies before fatal turn | 82.8% | 76.5% | 84.1% |
| Damage in fatal episodes on turns starting with 2+ adjacent enemies | 71.1% | 65.2% | 67.5% |
| Low-HP turns spent attacking, fatal episodes | 56.4% | 55.9% | 44.9% |

Death -4 reduces overall mortality and the fraction of damage in fatal episodes
associated with crowding, but does not markedly reduce the fraction of low-HP
turns spent attacking within those episodes. It would overstate the evidence to
say it has learned reliable disengagement. The completion-focused policy spends
a smaller fraction of low-HP turns attacking in fatal episodes yet dies much
more often: reducing attacks alone is not equivalent to effective survival.
These statistics condition on death and cannot identify the causal behavior
change by themselves. The main crowding pattern persists.

Artifact: `results/vision15-rewards-death-diagnostics.json`. Counterfactuals remain
one-turn hindsight probes, not proofs of avoidable episode deaths.
