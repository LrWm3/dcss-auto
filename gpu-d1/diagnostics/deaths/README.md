# Death diagnostics for the 10M no-travel policies

Read-only evaluation of fixed-512, fixed-2048 and 512-to-2048 curriculum
checkpoints. No retraining, controller override or observation change. All use
2048 physical turns, elapsed turns / 2048, sampled actions with seed 900000,
and the original 32 validation layouts x 32 episodes. No test layouts used.

Run from repository root:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/deaths/run.py
```

Requires the three retained 10M snapshots and original corpus. Compiles a CUDA
extension including the unchanged curriculum simulator. The extension records
pre-action HP, adjacent enemies (including sleepers), awake enemies within
three tiles, visible/awake counts, kills, action category and empty neighboring
floor moves that would reduce adjacency before enemies respond. Damage and
attack counts are differences in native cumulative combat counters, including
terminal turns. These counters survive episode reset. Full-health HP is 18;
regeneration adds 0.23 HP of progress per turn (integer healing on crossing 1).
Low health means at most 25% HP (integer HP <=4).

For each death, replay all mask-valid actions from the exact pre-fatal state,
including the original simulator RNG. Report which survive one turn and which
are empty-floor moves reducing the number of adjacent enemies before enemy
movement. Every original fatal action must reproduce death. Alternatives are
not offered to the policy. The extension's state, observations, masks and step
outputs must exactly match ordinary simulation for the first 128 steps of each
policy (393,216 environment-step slots, with ended episodes frozen). Complete
clear/death/timeout/kill/turn metrics must reproduce earlier evaluations exactly.

Interpretation limits:

- This is descriptive analysis of one training seed and one evaluation seed.
- Damage grouped by pre-action adjacency is an association; enemies can move
  during the turn. It is not a count of distinct damage-dealing attackers.
- A neighboring tile with fewer adjacent enemies is not necessarily a safe
  escape route: enemies pursue, act at different speeds, and can surround it.
- Counterfactuals hold the RNG state fixed, but different actions consume random
  draws differently. Selecting among nine outcomes exploits hindsight. Surviving
  one turn does not establish that the episode, or even the fight, is avoidable.
- Successful episodes last longer, so aggregate damage/turn exposure comparisons
  are affected by duration. Death-conditioned statistics do not establish cause.

Traces are bounded (~128 MiB per policy) in memory and discarded. Only aggregate
statistics and compact per-death records are saved. Existing ignores exclude
compiled code and logs. Results: `gpu-d1/results/vision15-death-diagnostics.json`.
