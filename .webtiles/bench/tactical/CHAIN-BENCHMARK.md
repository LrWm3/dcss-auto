# Back-to-back encounter benchmark — 2026-09-10

Implemented in `benchmark_chains.py`, `chain_bridge.lua`, and the opt-in native
`you.tactical_wave` binding. This is an evaluation harness, not a deployed policy
or a new training dataset. No validation/test seeds were used.

## Semantics

Keep one checkpoint character and its current floor. Remove original monsters
once, then spawn successive **different synthetic enemy groups** on visible floor
three tiles from the player's current position. No teleporting, reset, automatic
rest, or extra turn between waves. Gear, skills, attributes, inventory, HP, MP,
statuses, berserk duration/penalty, cooldown and position carry through naturally.
Normal combat regeneration, XP/level-ups and berserk kill extensions still occur.
The existing checkpoint adapter normalizes HP once at initial launch only.

Advance only after all tracked monsters in a wave are actually dead, not when
they leave sight. The current recipe whitelist excludes summoners and special
death effects that would require tracking additional actors. Failed placement
invalidates the trial; it is not a gameplay defeat or a skipped wave.

Monster construction uses a separate deterministic RNG subgenerator. Combat RNG
continues uninterrupted. Wave creation checks HP, max HP, MP, max MP, position,
turn, elapsed time, berserk penalty and **all** duration counters before/after.
Hidden actor tracking is lab metadata, not a learned-policy feature.

Final success requires all waves dead plus the existing full-health, clean-state,
20-quiet-turn recovery check. Otherwise death or a 320-action truncation. No
intermediate recovery endpoint. The action mask forbids berserk while berserking,
recovering, confused, or otherwise unavailable. Failed ability attempts can retry;
an activation is counted only if berserk actually starts.

Three fixed policies share the same one-action-at-a-time pursuit:

- `never`: no berserk.
- `every_wave`: activate within two tiles when legal, at most once per wave.
- `last_wave`: same trigger, but only in the final wave. This is a deliberately
  **wave-aware comparison policy**, not a deployable model with ordinary sight.

## Results

Three training checkpoints: seed 83017001 at XL5/47 HP, seeds 83019003 and
83018003 at XL6/56 HP. Each batch has two/three-wave recipes, both orders and two
combat RNG offsets: **24 chain variants × 3 policies = 72 runs**.

| Batch / policy | Fully recovered | Died | Truncated/stalled |
| --- | ---: | ---: | ---: |
| Single-monster waves: never | 23 | 1 | 0 |
| Single-monster waves: every wave | 24 | 0 | 0 |
| Single-monster waves: last wave | 24 | 0 | 0 |
| Enemy groups: never | 5 | 19 | 0 |
| Enemy groups: every wave | 17 | 7 | 0 |
| Enemy groups: last wave | 12 | 12 | 0 |

Single-monster recipes: hound → ogre; hound → iguana → ogre, and reversals.
Harder recipes are saved in `chain-recipes-groups.json`:
orc warrior + iguana → ogre + hound; hound + iguana → orc warrior + hound → ogre,
and reversals. These are curated stress tests, not a representative difficulty
distribution or intact original saved encounters.

**Saving berserk won three paired variants where early use died; early use won
eight where saving it died.** At least one policy recovered on 20/24 variants.
The remaining four are not yet evidence that a different berserk decision alone
can solve them. Individual paired outcomes can also depend on combat RNG; this
pilot does not establish statistical superiority on unseen encounters.

Concrete case: group case 13, seed 83017001, offset 1:
hound + iguana → orc warrior + hound → ogre. Early use activated on turn 3226.
On turn 3239 the third wave began at **33/55 HP, slowed and on berserk cooldown**.
No rest or clock advance occurred at the boundary. The ogre killed the character
on turn 3242. Saving berserk activated in wave 3 on turn 3246 and fully recovered.
Never berserking also died. Death morgues and full action/observation traces are
retained in the run directories.

Short chains can favor early use: the same rage can span multiple fights. We
should retain both kinds of examples rather than forcing an early-use penalty.
Next useful experiment: train/re-evaluate a per-action berserk gate against total
chain recovery, withholding future wave descriptions from its inputs. Keep all
variants and orderings of each source seed in the same dataset partition.

## Verification and artifacts

- `chains-smoke-v1` and `chains-repeat-v1`: all 12 full replays matched canonical
  observations/actions exactly.
- `chains-pilot-v1`: 72 simple-wave runs; no harness errors.
- `chains-groups-v1`: 72 group runs; no harness errors.
- `chains-groups-v2`: all 72 group runs repeated with corrected/expanded native
  timer diagnostics and a latched transition-error guard; all 5,712 actions and
  common canonical observation fields matched v1 (excluding the three newly
  added diagnostic fields). Audit passed 83 inter-wave handoffs and 85 combat
  states with berserk recovery/cooldown active; berserk remained masked.
- `audit_chains.py` checks actual wave transitions, state preservation, masks,
  action/reward traces, full recovery and death-evidence hashes.
- 221 Python tests passed, including 13 embedded Lua regression checks reported
  by the suite. Historical `crawl-tactical-sim` binary remains unchanged.

Artifacts live under `.webtiles/bench/tactical/artifacts/`; each batch includes
case/config hashes, private engine-specific cache, `trials.json`, `summary.json`
and per-worker action/observation logs. Audited batches additionally have
`audit.json`. Native v1 reported the legacy `DUR_EXHAUSTED` field; current Crawl
uses `DUR_BERSERK_COOLDOWN`. All raw durations and the correct RC cooldown mask
were already preserved in v1. V2 adds the correctly named native duration plus
elapsed time and berserk penalty; this is diagnostic, not a gameplay change.

## Reproduce

From the workspace root (use a new output directory):

```sh
make -C crawl-0.35/crawl-ref/source WEBTILES=y GAME=crawl-tactical-chain-v2 -j4 crawl-tactical-chain-v2
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/benchmark_chains.py --engine crawl-0.35/crawl-ref/source/crawl-tactical-chain-v2 --output /absolute/new/chains --recipes .webtiles/bench/tactical/chain-recipes-groups.json
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_chains.py /absolute/new/chains
```

Omit `--recipes` for the simple waves. Use `--config existing/config.json` with a
new `--output` for an exact replay, then `audit_chains.py REPLAY --compare ORIGINAL`.
The native binding is disabled unless `DCSS_TACTICAL_CHAIN=1`; the runner enables
it only for private offline workers. Placement currently uses a deterministic
visible-floor ring, not a general arena/pathfinding generator; extend that before
using arbitrary water/glass-heavy maps. The current pilot had no placement stalls.

Source archive: `engine-patches/tactical-chain-l-you-cumulative.patch` is the full
`l-you.cc` delta against nested Crawl commit
`ff61f77f9cb9bc203635fe8d9b8c73c4b5e0c7c3`. It includes earlier augmentation and
character bindings: do **not** apply it on top of their overlapping patches.
It is a zero-context patch; applying it requires `git apply --unidiff-zero`.
The other existing FIFO/simulation source changes are still required.
Final binary SHA256:
`cd5e4319af5ff5e8384a4d6f9545c9e2bc70d66ac885a383323c523840815264`.
