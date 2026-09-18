# minGRU navigation screen

This replaces only the recurrent core of the optimized symbolic policy. It keeps
15x15 local terrain/tactical crops, the 16x16 global map, 128 hidden units,
action masks, demonstrations, D4 augmentation, Adam settings, and the sequence
protocol (16 burn-in + 16 learning steps). One seed, 12,000 optimizer updates;
validation selects the checkpoint. This is supervised/DAgger on synthetic 32x32
navigation maps, not PPO or full-size Crawl quality testing.

## Implementation and checks

`symbolic_mingru.py` follows the positive-state minGRU recurrence from
[Were RNNs All We Needed?](https://arxiv.org/abs/2410.01201): one bias-free
projection produces candidate and gate; neither depends on the previous state.
The candidate is x+0.5 for x>=0 and sigmoid(x) otherwise. It is positive, not
upper bounded. Initial memory is zero; subsequent states remain nonnegative.

The parallel path uses an inclusive affine prefix scan of transitions
h'=a*h+b. Composition is (a2*a1, b2+a2*b1). This avoids intermediate exponential
overflow in the submitted code, as well as cancellation of large cumulative
logs. The PyTorch scan has O(log T) stages and O(T log T) work; it is not a fused
custom GPU kernel. Rollout uses the same recurrence one step at a time. Under
autocast the projection can use low precision, but recurrence arithmetic and
stored memory remain FP32. FP64 is preserved for numerical checking.

`check_symbolic_mingru.py` checks sequential/parallel outputs and input, initial
state and parameter gradients; zero/nonzero initial memory; chunk continuity;
long sequences and extreme projections; the original z=.99 overflow case;
CUDA FP16 autocast; and the actual padded replay loss and encoder/core gradients.
Sequences cannot span episode resets. The existing replay format has either a
full or empty burn-in prefix and only suffix padding in the learning window;
padding is excluded from loss. Stateful evaluation resets at each new batch of
episodes. No GRU hidden state/checkpoint is reused as minGRU memory.

The core has 49,664 parameters versus 124,416 for GRU; total policy size is
154,724 versus 229,476. Smaller capacity and different memory dynamics mean this
is an architecture comparison, not behavior-preserving optimization.

## Reproduction

From repository root:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/check_symbolic_mingru.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/benchmark_mingru.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/symbolic_run.py --kind mingru --updates 12000
gpu-d1/.venv/bin/python gpu-d1/diagnostics/remembered-grid/symbolic_interventions.py --kind mingru
```

Benchmark in isolation. Training refuses to overwrite an existing latest
checkpoint. Only best/latest checkpoints and bounded replay are retained;
generated models/maps/logs remain under ignored `learning-runs/remembered-grid`.

## Compute

See `results/symbolic-mingru-benchmark.json`. These are freshly initialized
networks measured on 80x70 inputs, with the same four PPO-shaped optimizer
passes and step inference. They exclude simulator, buffer and GAE costs.
They are not measured end-to-end PPO throughput.

| Workload | Optimized GRU | minGRU |
|---|---:|---:|
| FP32, batch 256, optimizer ms | 10.01 | 14.13 |
| FP32, batch 256, network decisions/s | 6,113 | 4,386 |
| FP16 autocast, batch 4096, prepared inputs, optimizer ms | 18.67 | 18.63 |
| FP16 autocast, batch 4096, prepared inputs, network decisions/s | 40,465 | 40,348 |

No speed advantage in this implementation/workload. An unfused scan's launch
and autograd costs matter at short sequence lengths, and all CNN/preprocessing
costs remain. A fused scan may change that; it has not been measured here.

## Navigation results

Completed all 12,000 updates: 2,636,427 valid supervised examples and 458,992
collected environment decisions. Training time excluding evaluation was 322.1 s
(5m22s). Validation selected update 10,000. The historical GRU ran 12,000 updates
and selected update 12,000, with 2,634,245 examples and 544.1 s training. Its
training used the original unfused implementation, so that wall-time comparison
is not evidence that minGRU is faster than optimized GRU; use the matched network
benchmark above for that question.

Greedy held-out exit rates:

| Case | Episodes | GRU | minGRU |
|---|---:|---:|---:|
| Known stairs | 256 | 91.80% | 95.31% |
| Exploration | 256 | 94.53% | 86.72% |
| Long known stairs | 128 | 77.34% | 90.63% |
| Long exploration | 128 | 81.25% | 71.88% |
| Threat backtracking | 32 | 100% | 100% |
| Long threat backtracking | 32 | 100% | 100% |

All minGRU failures in these evaluations were timeouts, with no deaths. Ordinary
exploration reversals increased from 2.90 to 13.61 per episode; long exploration
from 39.70 to 58.85. Long known-stair reversals decreased from 36.85 to 13.31,
and mean turns decreased from 157.19 to 101.89. Sampled minGRU evaluation achieved
94.53% known-stair and 90.23% exploration success. These are one-seed results,
with the same map splits and selection rule, not proof of a general architecture
advantage or disadvantage.

## Memory and global-map diagnostics

Resetting memory every action caused 0% success in all three ordinary test
groups, as it did for GRU. The minGRU policy does use its recurrent state.

Erasing the entire global embedding reduced minGRU known-stair success from
95.31% to 44.14%, while exploration changed from 86.72% to 85.16% and threat
backtracking remained 100%. In contrast, original GRU known-stair success was
91.80% normally and 92.97% with the embedding erased. This supports a stronger
global-input dependence in the trained minGRU policy. It does not establish
correct route planning: erasure also removes the global player marker and is an
out-of-distribution intervention.

On the 24 paired distant-goal cases (identical local inputs, fresh hidden state,
different remote stairs), minGRU chose both initial directions correctly in
7/24 pairs versus GRU's 3/24. Individual action accuracy was only 58.33% versus
56.25%; erased-global results were 0/24 pairs and 50%. Thus global-goal use is
still inconsistent despite the stronger erasure effect.

The smaller recurrence is viable and changed the learned behavior: better
known-goal navigation, weaker exploration, and greater reliance on the global
input in known-goal episodes. It is not a universal quality upgrade and, with
this unfused scan on short sequences, it did not improve matched compute cost.

Artifacts: `results/remembered-grid-symbolic-mingru.json`,
`results/remembered-grid-symbolic-mingru-interventions.json`, and
`results/symbolic-mingru-benchmark.json`. Checkpoints and source hashes are in
`learning-runs/remembered-grid/symbolic-mingru/`; the intervention artifact records
the evaluated checkpoint hash.
