# Tactical follow-up results

All 24 training jobs and their queued evaluations completed. Total sequential
pipeline time: 16,459.8 seconds (4h 34m 20s), including evaluation. All scripted
controls reproduced the reference results exactly. Three training seeds per
placement and intervention; percentages below are means across seeds.

## Clumped training

The distant-pocket case is six tough enemies, 12 player HP, a six-step retreat,
and four orientations. Natural clear means the policy chooses the retreat itself.
Contact waiting is measured after the full retreat is forced, while an enemy is
adjacent at the pocket. Thus these columns separate reaching shelter from using it.

| Configuration | Ordinary-floor validation clear | Natural pocket clear | Clear after forced retreat | Contact waiting |
|---|---:|---:|---:|---:|
| Original, 30M | 77.31% | 24.37% | 66.72% | 32.29% |
| Unchanged, 100M | 85.87% | 23.96% | 65.95% | 31.88% |
| Targeted practice, 100M | 86.17% | 50.11% | 82.85% | 1.05% |
| Enemy-set pooling, 30M | 78.91% | 7.57% | 69.25% | 28.16% |
| Exact D4 averaging, 30M | 88.74% | 46.32% | 83.32% | 1.28% |

Targeted practice beats the unchanged 100M control on natural pocket clears in
all three paired seeds: 43.2/52.2/54.9% versus 17.0/25.2/29.6%. Its natural
pocket clears also rise from 35.5% at 50M to 40.5% at 75M and 50.1% at 100M.
Unchanged training gives 23.7%, 25.1%, and 24.0% at those checkpoints.

## Unclumped training

| Configuration | Ordinary-floor validation clear | Natural pocket clear | Clear after forced retreat | Contact waiting |
|---|---:|---:|---:|---:|
| Original, 30M | 78.26% | 11.41% | 61.60% | 37.43% |
| Unchanged, 100M | 85.64% | 16.34% | 81.12% | 7.19% |
| Targeted practice, 100M | 86.52% | 30.68% | 82.29% | 1.77% |
| Enemy-set pooling, 30M | 79.62% | 7.49% | 72.88% | 22.61% |
| Exact D4 averaging, 30M | 88.22% | 6.87% | 83.14% | 1.49% |

Exact symmetry fixes pocket defense much more reliably than choosing the distant
retreat: the unclumped D4 model still seldom reaches and wins in that pocket.
Clumped experience remains useful despite removing orientation inconsistency.

## Shared-state and held-out checks

On the identical frozen first-contact observations, clumped mean wait probability
is 28.9% originally, 29.8% after unchanged 100M, 3.4% with targeted practice, and
3.9% with D4. These comparisons do not depend on each policy visiting different
combat states. D4 orientation inconsistency is approximately zero by construction;
its improved combat outcomes are the empirical result, not that identity itself.

On the separate held-out tactical layouts, clumped clear rates are 68.6% originally,
66.5% unchanged 100M, 81.8% targeted 100M, and 78.1% D4 30M. Unclumped rates are
58.8%, 54.3%, 74.9%, and 59.5%, respectively. This supports a targeted-experience
benefit beyond memorizing exact training layouts. These layouts remain related to
the training scenario family; this does not establish arbitrary tactical reasoning.

The 10% tactical-episode mixture supplied only 0.66% (unclumped) / 0.71% (clumped)
of additional training decisions. The intervention also changed short-episode and
clear-reward exposure, so the effect cannot be attributed solely to geometry.

## Compute and interpretation

Mean added training time for the unchanged 30M-to-100M continuation was 8.75 minutes
unclumped / 10.69 clumped; targeted continuation took 10.30 / 12.26 minutes.
Fresh D4 30M training took 9.69 / 10.53 minutes, versus historical ordinary MLP
30M times of 3.68 / 4.49 minutes. Enemy-set 30M took 4.75 / 5.57 minutes.
Training time excludes evaluation; D4 also requires eight views per inference.

More ordinary training improves general clears and hallway performance, but does
not reliably remove pocket waiting or teach distant retreat. Targeted practice
strongly improves both pocket use and retreat, without a large ordinary-floor
clear tradeoff in these runs. Symmetry is the best ordinary-floor model in this
screen and improves defense; it does not independently solve retreat discovery.
Removing record order through this particular pooled architecture is not an
improvement for the distant-pocket task. That does not prove order sensitivity is
irrelevant: pooling changes capacity and representation as well as invariance.

These are three-seed comparisons, not formal significance tests. Repeated combat
rollouts and rotations are not independent training seeds. See
`results/tactical-next-comparison.json` for per-seed and intermediate results,
`results/tactical-next-training-summary.json` for training/validation details,
and `TACTICAL-NEXT.md` for experimental definitions.
