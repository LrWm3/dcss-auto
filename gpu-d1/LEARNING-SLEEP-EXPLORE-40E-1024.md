# 40-enemy, 1024-turn learning runs

These are single-seed (`seed=1`) 100M-decision runs on the corrected single-map
environment. The only experiment change from the current setup is increasing
the enemy count from 8 to 40 and the decision deadline from 512 to 1024.
Both runs retain sleep, doubled first-seen exploration reward, remembered walls,
and the existing ring/frontier observation variants.

Evaluation uses 1,024 episodes on the same fixed map (`eval_seed=900000`).

Audit caveat: the recorded `src/learn.cu` source places player HP, time, and
coordinates at offsets 202–205, which overlap the ninth monster's first four
features when compiled with 40 enemy slots. The intended player block is
362–365. The scores below describe that old encoding; a corrected experiment
needs a fresh single-map reference. This does not affect the eight-enemy v2
encoding. See [the next experiment design](EXPERIMENT-RING-GENERALIZATION.md).

| variant | sampled clear | greedy clear | sampled kills | train speed |
| --- | ---: | ---: | ---: | ---: |
| 11x11 ring | 70.996% | 54.590% | 32.966 / 40 | 125.7k decisions/s |
| frontier memory | 71.582% | 46.582% | 33.193 / 40 | 118.0k decisions/s |

For reference, pursuit clears 68.652% on this same 40-enemy evaluation;
wait and random clear 0%. The stochastic policy is stronger than its greedy
projection in both variants, so the sampled scores are the primary comparison.

Run directories:

- `learning-runs/sleep-explore-ring-walls-40e-1024turn-100m-seed1`
- `learning-runs/sleep-explore-frontier-memory-walls-40e-1024turn-100m-seed1`

## D:1 floor corpus

`fixtures/d1-corpus-388/` contains 388 unique static layouts selected with
`unsupported_tiles=0` and no nonzero map markers. Every map was compiled with
the native LOS consistency check. The fixed seed splits are:

- `train`: 256 maps
- `validation`: 32 maps
- `test`: 100 maps

The older v2 multi-map environment now loads the full corpus. The ring/frontier
environment still requires a multi-map port that preserves its task semantics.
