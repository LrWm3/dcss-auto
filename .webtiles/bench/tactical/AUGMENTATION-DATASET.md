# Automatic encounter augmentation and labeling

`augmentation_dataset.py` builds a versioned synthetic training supplement from
verified encounter indexes. It does not modify the originals, train a model, or
deploy a production RC. `augmentation-all-v1.json` covers the current development
and separately reserved fresh-evaluation collections, including explicit records
for their quarantined encounters.

## Run

From the repository root, with Python plus `pexpect` available:

```sh
export DCSS_TACTICAL_ENGINE="$PWD/crawl-0.35/crawl-ref/source/crawl-tactical-augment"
export DCSS_TACTICAL_AUGMENT=1
python .webtiles/bench/tactical/augmentation_dataset.py \
  .webtiles/bench/tactical/augmentation-all-v1.json \
  .webtiles/bench/tactical/artifacts/augmentation-all-v4
```

Add `--resume` to reuse completed families after an interrupted run. The config,
source hashes, engine hashes, dataset indexes and split assignments must match.
Partial family attempts are preserved and rerun in a new attempt directory.
Completed quarantines remain quarantined; use a new versioned output after fixing
their cause. Do not run two writers against the same output directory.

For an orchestration/comparison-only repair, `--reuse OLD_OUTPUT` starts a **new**
output and reuses fully generated families after checking their verification,
trial and neutral-reference trace hashes. Recipes, dataset entries, split inputs,
engines and gameplay-source hashes must all match. Incomplete families are rerun.
The new manifest links the old manifest and each reused family links its source
evidence. Retain the old output: reused checkpoints and traces are referenced,
not duplicated. Ordinary `--resume` still requires every source hash to match.

A single automatic retry is allowed for the identified Lair map-parser startup
failure, only before any observation or action. Its terminal log must match the
specific error. The original failure is retained under `startup_attempts`; the
retry uses the same checkpoint and recipe. Deaths, stalls, arbitrary errors and
failures after gameplay starts are never retried to obtain a better label.

Independent families run in separate worker processes, each with its own game,
so Python geometry/JSON work does not share one interpreter lock.

The separate opt-in engine build is described in `AUGMENTATION-PILOT.md`.

## Protocol

1. Enumerate every input encounter. Keep ineligible original captures in coverage
   as quarantined; never turn their unverifiable saves into training data.
2. Verify original save/RC checksums and replay-readiness. Add the enhanced goal
   bridge to a copy, then collect a short reference on its original engine.
3. Replay those same actions on a neutral copy using the augmentation engine.
   Require matching normalized observations throughout the prefix.
4. Create each configured HP/RNG recipe from the immutable original save.
   Reset twice and compare the first observation and up to 12 controller decisions
   (or death). The initial observation may differ only in the requested HP field.
5. Run withdraw, defend and pursue, each with berserk forbidden/permitted, from
   exactly the same variant. Each trial is bounded by 600 decisions, 1500 turns,
   and the existing no-progress limits.
6. Audit successful trials for full health, observable safety and 20 checked quiet
   turns; audit deaths for a recorded terminal transition. Keep errors, stalls,
   timeouts and unavailable policies separate.
7. Label each variant with its successful, failing, unavailable and unknown
   strategies. Admit it only when all six comparisons are accounted for, at least
   one strategy recovers, at least one dies, and its parent seed belongs to train.

The three initial recipes are full HP/RNG offset 17, 80% HP/original RNG, and
60% HP/RNG offset 1. Percentages refer to maximum HP, not current HP: the first
recipe can heal a partially injured original. RNG draws perturb the future
gameplay stream without reseeding the dungeon. These are recipe-backed resets,
not edits to the binary save. Prefix checks are bounded verification, not a proof
that every arbitrarily long replay is deterministic.

## Outputs and training integration

- `manifest.json`: frozen source/input/engine hashes and all original entries.
- `coverage.json`: each parent's generation status, failures, neutral check,
  variant verification and trial evidence.
- `labels.json`: the complete strategy-label matrix, including all-win, all-loss,
  unresolved and held-out variants. These remain useful even when not selected.
- `results.json`: all individual strategy outcomes with trace hashes.
- `training-index.json`: only qualifying mixed-outcome variants of training seeds.
- `training-rows.json`: audited win/death rows for those selected variants; excludes
  unavailable policies and all unverified or incomplete comparisons.
- `summary.json`: coverage, outcomes, selection counts and split breakdown.

The supplement can feed the existing goal outcome fitter:

Run Python with `.webtiles/bench/tactical` on `PYTHONPATH` and the same lab-engine
environment as above.

```python
from augmentation_dataset import load_training
from run_goals import fit

rows = load_training(output_directory)  # verifies hashes, seeds, traces and splits
# Only when explicitly choosing to retrain:
model = fit(rows)
```

The pipeline itself never calls `fit`. The existing default training config is
not silently redirected. Selected recipe cases retain their low-level lab-only
metadata; training readiness is granted by the audited supplement index, not by
misrepresenting them as original production-engine checkpoints.

All variants of a seed keep that seed's partition, even across multiple source
encounters. Validation/test/fresh-evaluation variants are labeled but never
included in `training-rows.json`. Unassigned seeds likewise cannot enter train.
Recipe IDs and RNG offsets are provenance, not model features.

Mixed-outcome selection deliberately enriches difficult decisions and is not a
representative evaluation distribution. Keep the complete labels, retain original
training encounters when fitting, and evaluate on unfiltered held-out families.
Repeated variants are correlated examples, not independent new seeds. Consider
family weighting and multiple RNG continuations before claiming calibrated win
probabilities or improved generalization.

## Regressions fixed before collection

- Death morgues can report negative HP after overkill. The parser now recognizes
  zero or negative HP, while retaining private-directory, character, seed and
  non-stale-turn checks. Positive-HP dumps remain rejected.
- Map memory can retain an invisible-monster marker long after it leaves LOS.
  Such a remembered marker no longer blocks recovery. Visible disturbances,
  `unseen`, unsafe state, damage and harmful statuses still block success.
- Replay comparison ignores death-evidence file paths/checksums, which differ
  between resets and between terminal-message versus morgue death detection.
  The raw evidence stays in the trace and remains audited separately; actual
  state differences are not normalized away.

Targeted replay of the original ogre 60% HP/RNG-zero variant now records the
no-berserk death at decision 37 and berserk-permitted recovery at decision 182
(61/61 HP and 20 quiet turns). The old results were a missed death after 36
recorded transitions and a stall at decision 242, respectively. Evidence:
`artifacts/augmentation-bugfix-v1`.

## Broad demonstration

The completed v4 run covers every usable encounter in the two configured indexes:

| Coverage | Count |
| --- | ---: |
| Indexed original encounters | 118 |
| Verified originals successfully augmented | 112 |
| Pre-existing quarantined originals | 6 |
| Replay-verified synthetic variants | 336 |
| Strategy comparisons | 2,016 |
| Mixed-outcome training variants | 31 |
| Selected training rows | 180 |
| Mixed-outcome fresh-evaluation variants, excluded from training | 13 |

All 112 usable parents produced all three recipes and all six strategy outcomes.
The six old captures failed original replay fidelity checks and are explicitly
accounted for, not silently used as reliable examples. Three trials stalled;
these make their variant labels incomplete and are excluded from training.
One zero-observation engine startup error was repaired in v4 by the bounded
retry policy above: the single retry recovered at decision 96 with 55/55 HP and
20 quiet turns. Its variant is all-win, so training selection is unchanged.
v4 reuses the completed v3 evidence, without rerolling any gameplay outcome.
No model has been fitted or deployed.

Final outcomes: 1,816 audited recoveries, 113 audited deaths, 84 unavailable
choices and three unresolved stalls. The coordinator and training-loader audit
exited successfully. All 161 Python tests and 13 Lua checks pass. Original save
and RC hashes, the production RC, model and seed partitions remain unchanged.
The v4 export preserves 2,015 v3 trial records exactly and adds only the one
pre-observation retry, with its original attempt retained.

Tracked provenance and checksums: [evidence/augmentation-all-v4.json](evidence/augmentation-all-v4.json).
Final files: `artifacts/augmentation-all-v4/{summary,labels,training-index,training-rows}.json`.
The supplement is ready for explicit use through `load_training`; the default
training corpus/config has not been silently replaced.

The additional stalls expose two remaining controller limitations: waiting
while held in a web after enemies disappear (two held-out trials), and waiting
near unreachable visible enemies (one training trial). They are not the fixed
stale invisible-marker bug and are not labeled as deaths.

Examples of useful training contrasts:

- `development/mining-deeper-v1/collection/encounter-007/variant-02`:
  D:4 orc priest and three orcs, 28/47 HP, RNG offset 1. Both pursue options
  recover; both withdraw and both defend options die.
- `development/mining-fresh-training-v1/collection/encounter-019/variant-00`
  and `variant-01`: Jeremiah encounter. Defend/pursue with berserk permitted
  recover; their no-berserk counterparts die; withdraw is unavailable.
  The harder `variant-02` loses with all available options and is not selected.

These compare complete recipes, not isolated causal effects of lowering HP:
the recipes also differ in RNG offset. They do not establish model improvement.

The initial run `augmentation-all-v1` was stopped after finding a false replay
mismatch: both copies died on decision 7, but only one terminal observation
included morgue provenance. The comparator fix passes that live regression in
`augmentation-terminal-check-v1`. `augmentation-all-v2` aborted during reuse
directory creation before launching games; the directory bug has a regression
test. `augmentation-all-v3` completed collection under the corrected implementation
and reuses 18 verified complete families (324 trials) from v1. No raw evidence was
deleted and no tactical controller changed during these orchestration repairs.
