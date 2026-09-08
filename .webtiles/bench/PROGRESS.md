# Progress journal

## 2026-09-07: establish worst-seed objective

Historical original: ranks `[4, 7, 7, 6, 11]`, minimum **4**.
Historical resilience-v2: `[13, 2, 7, 11, 10]`, minimum **2**.
The latter is a regression, despite its best seed reaching Lair:2.
Historical code snapshots are unavailable; hashes are recorded only when known.

Checkpoint `5b7b6c5` preserves the current bot and regression suites.
Unrelated workspace files are deliberately not staged.

Next candidate: `threat-berserk-v1`. Restore the original adjacent yellow/red
berserk trigger, removing crowd-only activation and the HP floor. Keep emergency
resource use and the stat-zero gear guard. Hypothesis: crowd-triggered rage can
expire before later threats, harming the weakest early-game seed. This is a
testable hypothesis, not an established causal diagnosis. Evaluate all five seeds
without intervention; judge the minimum first. Results go into runs.jsonl.
