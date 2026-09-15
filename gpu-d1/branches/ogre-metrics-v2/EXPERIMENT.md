# Two ogres, 30M → 150M continuation

Seed 0 continues the completed `ogre2-baseline-30m` checkpoint, including optimizer, live worlds and RNG. 24 required ordinary enemies, two optional slow ogres; 256 training layouts, 32 validation layouts × 32 episodes, 1024-turn budget. Policy inputs, rewards, training parameters, native State ABI and simulation behavior are unchanged. The fast BFS, smaller block launches and masked evaluation were ported after 55,607,296 decisions; the fast phase is in the separate `ogre2-baseline-150m-fast` suite.

A separate `gpu-d1/learning-runs/ogre2-baseline-150m` directory retains latest/best weights with bounded storage. `continuation.json` records the origin checkpoint hash and cumulative starting training time. The original 30M directory is preserved. Cumulative decisions stop at the first complete PPO update at or above 150M. Evaluations at the starting 30M checkpoint and 50/75/100/125/150M use fixed validation seeds and both sampled and greedy policies. Checkpoint saves also occur every 1M decisions. No new test-layout selection is performed.

Diagnostics, all computed without exposing new information to the policy:

- `ogre_death_rate`: episodes whose fatal blow was from an ogre / all episodes. This is direct fatal-blow attribution, not counterfactual causation.
- `ogres_killed`: mean number killed; `any_ogre_killed_rate`: fraction of episodes killing at least one.
- `ogres_woken`: mean wake events per episode; `ogre_wake_fraction`: wake events / two spawned ogres; `any_ogre_woken_rate`: episodes waking at least one. Unlike living-awake-at-end counts, wake events retain ogres subsequently killed.
- `awake_ogre_adjacent_turns`: mean player turns within Chebyshev distance 1 of any living awake ogre. `awake_ogre_near_turns`: within distance 3. Each turn counts once even with two ogres nearby; near includes adjacent. Measured after the player's action and wake checks, before monsters act; a final clearing action skips the monster phase and adds zero exposure. Corresponding turn fractions divide summed exposure by summed episode turns.
- `clear_with_any_ogre_alive_rate` / `clear_with_all_ogres_alive_rate`: fractions of all episodes clearing with at least one / both ogres alive. `all_ogres_alive_given_clear`: fraction among successful clears retaining both ogres.
- Legacy `ogre_adjacent_turns`, damage, actions, awake-at-end and living-at-end remain recorded.

Only the native output vector grows, 15 → 18. Three per-step outputs accumulate wake/adjacent/near measurements in evaluation; terminal measurements are captured before auto-reset. No persistent native counters are added, allowing exact live-world continuation.

Validation: full smoke training/evaluation passed. Original vs instrumented CPU trajectories retain identical observations, masks and original outputs over 8,400 world turns; all new outputs match CUDA and satisfy exposure bounds. Results/logs are in `gpu-d1/results/ogre-metrics-{smoke,parity}.log`.

Resume the launched run using:

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/ogre-metrics-v2/scripts/run_ring_ablations.py --variants ogre2_base --seeds 0 --steps 150000000 --output gpu-d1/learning-runs/ogre2-baseline-150m-fast
```

Progress: `gpu-d1/results/ogre2-baseline-150m-console.log`; checkpoint evaluation history: `gpu-d1/learning-runs/ogre2-baseline-150m/runs/ogre2_base-seed0/curve.json`. Training time is cumulative, including the original 536.258 seconds; subtract the value in `continuation.json` for continuation-only training time.

Current progress log: `gpu-d1/results/ogre2-baseline-150m-fast-console.log`. Current curve: `gpu-d1/learning-runs/ogre2-baseline-150m-fast/runs/ogre2_base-seed0/curve.json`. The original directory is frozen at the migration boundary.
