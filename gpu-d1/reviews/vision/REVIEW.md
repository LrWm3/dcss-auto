# Review of vision v1 after the four 30M runs

No confirmed wall-visibility implementation defect was found in the four configurations actually trained. The review did find unsupported legacy feature combinations and interpretation limitations. This is bounded verification, not a proof of all possible trajectories.

## Findings

1. **Latent compatibility bug, not active in these runs: healing.** `HEAL_CHARGES` selected a 12-value output buffer, while the new visibility diagnostics wrote through index 13. Its charge observation also collided with the appended visibility channel. Enabling this flag could corrupt memory or observations. None of the four jobs enables healing. A compile-time guard now rejects it.
2. **Latent information leak, not active in these runs: awake status.** The legacy `MONSTER_AWAKE_OBS` path writes every living monster's awake flag using original roster slots, without visibility gating or discovery-slot remapping. None of the four jobs enables this flag. It is now rejected, along with unsupported observation schemas. Future integrations need explicit layout and visibility handling.
3. **Enemy representation confound.** Global mode allocates all records at reset in roster order. Local mode allocates records as enemies are discovered, placing early encounters in early slots. A fixed-input MLP is sensitive to record order. The observed local/global difference therefore includes ordering and input sparsity, not only availability of enemy information. It does not establish that extra information itself is harmful. A future matched-order or permutation-aware representation comparison would isolate this better.
4. **Exploration reward interaction.** Walls change which floor cells are revealed and consequently when the policy receives exploration reward. This is consistent with the defined task, but the LOS comparison is not purely an input-masking experiment. A no-exploration-reward comparison would help separate this effect.
5. **Enemy awareness remains simplified.** Monsters wake within Chebyshev distance six even through walls; player vision is radius four. Awake monsters still pursue the actual player location. This was intentionally held fixed, and matched-action tests confirm visibility does not alter combat. It is realistic player occlusion, not a complete implementation of native perception/noise/monster memory.
6. **Metric wording.** `unseen_alive` means never physically encountered within the selected sensor rule (or attacked), including in global-information arms. In global arms these enemies are already known to the policy. Interpret that metric as not approached/encountered, not undiscovered. Previously encountered enemies currently out of sight count in `encountered_alive`.
7. **Memory scope.** Terrain is remembered; enemy locations are not. Hidden enemy records go blank and reappear in the same discovery slot on reencounter. Identity matching is perfect internally. The policy is feed-forward and does not receive stale enemy locations or a recurrent hidden state. These are deliberate simplifications, not a failure of the LOS lookup.

## Additional validation

- Replayed all four final checkpoints on the same 1,024-episode evaluation panel. Each final clear rate reproduced exactly.
- Audited 1,024 world snapshots per policy (4,096 total). Independently reconstructed all frontier memberships from remembered terrain, rebuilt a full BFS without early stopping, and compared target and route hints. Also checked current visibility, remembered wall/floor encoding, and floor-coverage counters. All error counters were zero. No frontier pointed to the current square without a route.
- Checked all 265,376 adjacent-square relationships from the 33,172 floor origins in the 32 validation maps. Every in-bounds adjacent square is visible in the native cached mask. Thus the feared case of an adjacent unseen corner leaving the current square permanently marked as a frontier does not occur in this corpus.
- Earlier checks covered 33,600 CPU/CUDA world steps, hidden-enemy mutation tests, masked terrain/movement information, exploration reward accounting, and matched combat outcomes across arms. Six native exports matched 9,710,400 cached visibility pairs.

## Changes and provenance

Only compile-time rejection of unsupported feature combinations was added to the simulator during this review; the four supported configurations have unchanged behavior. No training was relaunched.

`trained-learn.cu` preserves the exact pre-guard source whose SHA-256 matches the finished suite's manifest. The original suite libraries, checkpoints, and results remain unchanged. The runner deliberately rejects resuming the old suite against changed source; use the preserved source for exact historical reproduction or a new suite for future experiments.

`audit.py`, `audit.cpp.cu`, and `audit-results.json` preserve the read-only replay and independent frontier audit. Build the auditor with the standard vision defines, then run:

```sh
nvcc -O3 -std=c++17 -arch=sm_75 -ccbin /usr/bin/g++-12 -shared -Xcompiler -fPIC \
  -DLEARN_ENEMIES=40 -DMULTI_MAP -DSLEEP_ON -DEXPLORE_REWARD -DMARK_WALLS \
  -DFRONTIER_RING_MEMORY_WALLS_OBS -DKNOWN_FRONTIER -DFRONTIER_ROUTE_CUE_OBS \
  gpu-d1/reviews/vision/audit.cpp.cu -o /tmp/vision-review.so
gpu-d1/.venv/bin/python gpu-d1/reviews/vision/audit.py /tmp/vision-review.so
```

Post-guard verification: healing, awake-status, and full-map override builds were rejected as intended. The supported build compiled and matched the original local-LOS library over 1,024 CPU world steps.
