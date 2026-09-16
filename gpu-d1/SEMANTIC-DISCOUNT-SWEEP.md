# Fixed-policy discount sweep

Question: with reward amounts unchanged, which physical-turn discount factors
make the deterministic controller score higher than the frozen 10M model?

The diagnostic records the raw reward at every physical turn, including inside
macros. An isolated instrumentation library adds only reward tracing; original
training libraries are unchanged. Each replay must reproduce recorded per-episode
clears, turns, raw return and gamma=0.99 return. Trajectories are then rescored
without changing policy behavior, observations, turn budgets or termination.

Policies: deterministic reference, sampled and greedy learned policies, sampled
with forced rest, and sampled with forced rest plus waiting for awake enemies.
All use the existing 32 validation layouts × 32 placements. Rewards remain +1
kill, +3 clear, -4 death, -0.001 per physical turn, +0.002 revealed floor tile.

Per-turn traces remain under ignored `learning-runs/semantic-discount-sweep`.
Reproducer: `diagnostics/semantic-actions/discount_sweep.py`.
Compact results: `results/semantic-actions-discount-sweep.json`.

A grid from 0.99 to 1 finds sign changes, followed by bisection to locate their
crossings. These are empirical crossing points on this finite panel, not universal
constants. Paired bootstrap intervals resample the 32 layouts as clusters, keeping
all 32 placements within each layout; they do not include training-seed variation.

## Results

| Gamma per physical turn | Deterministic | Sampled model | Greedy model | Sampled + rest | Sampled + rest/wait |
|---|---:|---:|---:|---:|---:|
| 0.99 | 4.7243 | 6.0873 | 6.1390 | 5.1235 | 4.7231 |
| 0.995 | 8.4055 | 10.3451 | 10.4397 | 8.9868 | 8.4081 |
| 0.997 | 12.0799 | 14.0866 | 14.2181 | 12.6946 | 12.0887 |
| 0.998 | 15.1885 | 16.9710 | 17.1297 | 15.7386 | 15.2042 |
| 0.999 | 19.8893 | 20.9888 | 21.1837 | 20.2190 | 19.9175 |
| 0.9992 | 21.1065 | 21.9764 | 22.1799 | 21.3594 | 21.1383 |
| 0.9995 | 23.1578 | 23.6000 | 23.8176 | 23.2657 | 23.1960 |
| 0.9997 | 24.6967 | 24.7877 | 25.0155 | 24.6839 | 24.7399 |
| 0.9998 | 25.5236 | 25.4161 | 25.6493 | 25.4421 | 25.5695 |
| 0.9999 | 26.3918 | 26.0690 | 26.3077 | 26.2354 | 26.4407 |
| 0.99995 | 26.8422 | 26.4049 | 26.6465 | 26.6459 | 26.8926 |
| 1.0 | 27.3038 | 26.7474 | 26.9920 | 27.0658 | 27.3558 |

Empirical deterministic/model crossings: approximately 0.999747 sampled and
0.999861 greedy. Gamma=0.9999 therefore flips both point estimates, but is not a
statistically robust separation on this panel: paired-layout bootstrap intervals
for deterministic minus sampled and greedy returns are respectively [-0.014, 0.667]
and [-0.227, 0.394]. At gamma=1, the differences are +0.556 and +0.312, with
intervals [0.211, 0.907] and [-0.010, 0.631]. These are exploratory intervals on
reused validation maps and one training seed, not confirmation on held-out data.

Proposed first training configuration: gamma=1.0 per physical turn; retain the
existing reward amounts, -0.001 per-turn cost, 2048-turn terminal deadline,
observations and action interface. This removes discount-induced preference for
getting rewards earlier while preserving the explicit cost of taking extra turns.
The resulting episodic return is exactly the reported raw reward. Gamma=0.9999
is a milder alternative, but its margin over greedy is small here.

Implementation prerequisite: gamma is currently hardcoded as .99 inside native
macro reward accumulation as well as supplied to the PPO duration-dependent
bootstrap. Both must be changed consistently before training; changing only the
Python job's gamma would give an inconsistent return. No training configuration
or production library was changed by this diagnostic, and no new run was launched.

A ranking flip only establishes that these fixed behaviors are ordered more in
line with clears. It does not prove that PPO will learn the safer behavior, that
credit assignment is solved, or that the deterministic policy should dominate all
policies (the rest+wait hybrid has slightly higher raw return). Keep policy-learning
and generalization tests separate from this fixed-trajectory objective check.
