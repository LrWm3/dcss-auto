# RNG-offset chain variants — 2026-09-10

This is a follow-up to [CHAIN-BENCHMARK.md](CHAIN-BENCHMARK.md). It reruns the
same 12 harder encounter layouts (three training seeds × two chain lengths × two
wave orders) with `you.tactical_augment(100, N)` consuming N gameplay-RNG draws
before combat, for N = 1, 2, and 3. Each layout/policy/offset is a fresh isolated
process. The character and wave handoff semantics are unchanged.

There were 36 chains per policy, 108 runs total. The complete traces are in
`artifacts/chains-groups-offsets1-3-v1`; `audit_chains.py` passed all 108 runs,
including 134 actual wave handoffs, 155 combat states during cooldown/recovery,
and zero harness errors or stalls.

## Results

| RNG draws | Never berserk | Berserk every eligible wave | Save berserk for final wave |
| ---: | ---: | ---: | ---: |
| 1 | 2/12 | 8/12 | 7/12 |
| 2 | 2/12 | 11/12 | 8/12 |
| 3 | 6/12 | 10/12 | 6/12 |

The numerator is full recovery after the final wave; the remainder are deaths.
There were no truncations or stalls.

By chain length:

| RNG draws | Never, 2 waves | Every, 2 waves | Last, 2 waves | Never, 3 waves | Every, 3 waves | Last, 3 waves |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1/6 | 5/6 | 4/6 | 1/6 | 3/6 | 3/6 |
| 2 | 1/6 | 6/6 | 4/6 | 1/6 | 5/6 | 4/6 |
| 3 | 3/6 | 5/6 | 3/6 | 3/6 | 5/6 | 3/6 |

## What changed

The outcomes are sensitive to combat RNG, but the effect is not a simple “more
advancement is better/worse” curve. Across the 12 fixed layouts, outcome changed
between offsets 1/2/3 in:

- never berserk: 8/12 layouts;
- berserk every eligible wave: 4/12;
- save-last: 8/12.

Every-wave remained the strongest fixed policy in aggregate, but its recovery rate
was 8/12 → 11/12 → 10/12. Save-last was 7/12 → 8/12 → 6/12. Never was 2/12 →
2/12 → 6/12. This is enough variation to justify using multiple RNG offsets when
evaluating a berserk policy; one offset would overstate or understate particular
strategies.

The best evidence for a genuine berserk timing tradeoff remains the earlier
case where early berserk entered wave three at 33/55 HP, slowed and on cooldown,
then died to an ogre, while save-last recovered. The offset sweep adds robustness
testing around that idea; it does not establish that save-last is generally best.
The current sample has only three source seeds and synthetic groups, so do not use
these rates as a deployment estimate.

## Reproduce

```sh
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/benchmark_chains.py \
  --engine crawl-0.35/crawl-ref/source/crawl-tactical-chain-v2 \
  --output /absolute/new/chains-offsets \
  --recipes .webtiles/bench/tactical/chain-recipes-groups.json \
  --offset-start 1 --offsets 3
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_chains.py \
  /absolute/new/chains-offsets
```

Trial records now include `rng_offset` and `chain_length` directly. The runner
still keeps offset 0 as the default for compatibility; `--offset-start 1
--offsets 3` means exactly offsets 1, 2, and 3.
