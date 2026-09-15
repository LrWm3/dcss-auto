# Ogre results, 2026-09-15

All results below are completed seed-0 experiments. Ordinary evaluation uses 32 held-out layouts × 32 sampled episodes, with 24 required ordinary monsters plus the indicated optional ogres. Rates are final-checkpoint results, not best-checkpoint selections. Small differences need more training seeds.

## Longer two-ogre training

| Decisions | Clear rate | Ogre-inflicted deaths |
| --- | ---: | ---: |
| 30M | 24.12% | 47.56% |
| 50M | 30.66% | 45.12% |
| 75M | 34.28% | 41.50% |
| 100M | 32.62% | 46.39% |
| 125M | 35.06% | 44.92% |
| 150M | 39.84% | 41.11% |

At 150M the model averaged 17.94 required kills; 58.79% of episodes ended in death. All successful clears left both ogres alive. Improvement was uneven and the endpoint does not establish saturation. Total accumulated training time was 1,642 seconds (27.4 minutes), combining the original kernels and the fast phase after 55.61M decisions; it is not a pure fast-throughput measurement.

## Explicit optional-label ablation

| 50M configuration | Clear rate | Ogre-inflicted deaths | Training seconds |
| --- | ---: | ---: | ---: |
| Label present, fresh fast control | 30.66% | 45.12% | 315.2 |
| Label zeroed, fresh fast run | 29.00% | 45.90% | 331.1 |

Removing the explicit label did not improve the final result; the 1.66 percentage-point clear-rate difference is a single-seed observation. The model can still infer optional status from ogre type or fixed slot, so this does not remove all information about whether a kill is required.

## Small pressure curriculum

Each pressure scenario has one required monster and one optional ogre. Training uses 32 pressure layouts and evaluation uses 16 distinct canonical geometries, with 32 episodes per layout (512 held-out episodes). Ordinary evaluation remains separate.

| 50M training arm | Ordinary clear | Held-out pressure clear | Training seconds |
| --- | ---: | ---: | ---: |
| Ordinary only | 30.66% | 99.80% | 315.2 |
| 10% pressure resets | 28.61% | 99.41% | 319.3 |

The curriculum accelerated early learning: at 3M, held-out pressure clear was **74.22% versus 44.34%**; at 10M, ordinary clear was **10.74% versus 5.47%**. The benefit did not persist as a final advantage at 50M. Ordinary training alone reached 95.70% pressure success by 10M, and both arms approached ceiling by 30M. These scenarios demonstrate that ordinary training transfers to simple avoidance layouts, but are too easy to discriminate mature policies well.

The mixed arm consumed 763,601 pressure decisions, **1.53% of total decisions**, across 16,294 completed pressure episodes. Thus 10% of episode resets was a much smaller fraction of compute. Successful held-out pressure episodes left the ogre alive in both arms. Mean held-out ogre damage was 0.049 (ordinary-only) versus 0.371 (mixed); near-ceiling differences represent very few failures, not strong evidence of harm.

Full final metrics, per-map results, compact checkpoint curves and training-group counts are archived in [results/ogre-summary](results/ogre-summary). See [the pressure design](branches/ogre-pressure-v1/EXPERIMENT.md), [label ablation](branches/ogre-metrics-v2/NO-OPTIONAL-LABEL.md), and [performance measurements](PERFORMANCE.md).

The archive contains no model weights, live worlds or compiled map caches. Regenerate pressure maps with `gpu-d1/.venv/bin/python gpu-d1/branches/ogre-pressure-v1/scripts/generate_pressure.py`; ordinary corpus collection/compilation uses the scripts documented in the ablation runner and corpus experiments. Existing historical run paths in archived JSON identify local provenance and are not bundled training checkpoints.
