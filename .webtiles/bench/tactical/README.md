# Tactical encounter lab (prototype)

This is a separate local initiative. It does not change the production RC,
touch live tmux/WebTiles sessions, or port the old dcss-ai-wrapper.

## Run

Requires the existing Crawl binary and Python 3 with `pexpect` (available in
`/usr/bin/python3` on this machine). Run from the repository root:

```sh
/usr/bin/python3 .webtiles/bench/tactical/test_tactical.py
/usr/bin/python3 .webtiles/bench/tactical/bench.py capture \
  .webtiles/bench/tactical/artifacts/my-eustachio-case --warmup 35
/usr/bin/python3 .webtiles/bench/tactical/bench.py rollout \
  .webtiles/bench/tactical/artifacts/my-eustachio-case --action baseline --steps 140
/usr/bin/python3 .webtiles/bench/tactical/experiment.py \
  .webtiles/bench/tactical/artifacts/my-eustachio-case \
  --output .webtiles/bench/tactical/artifacts/my-experiment --episodes 8 --steps 140
```

Case and experiment destinations must be new; existing results are not replaced.
`--warmup` takes that many baseline decisions **after first Eustachio contact**,
before saving. Capture currently targets main seed 3, Minotaur Berserker, and
Eustachio explicitly. Other encounter types need capture configuration added.

## Environment contract

`Environment(workspace).reset(case_directory)` launches a private process from
an immutable checkpoint, checking engine/save/RC SHA-256. Each worker has its
own saves, macros, morgues, RC snapshot, and terminal transcript. `close()` stops
only that worker. Keep checkpoint directories when pruning worker artifacts.

`step(action)` returns the next observation and appends a transition. The initial
action set is eight movement directions, wait, Tab, adjacent-only autofight,
berserk, and one RC-controller decision (`baseline`). This is a **decision-level**
interface: Tab and RC decisions are macro-actions, not guaranteed single turns.
`turn_delta` records elapsed game turns; no-turn actions are not silently retried.

Observations use only CLua player-visible data: HP, statuses, visible relative
terrain/clouds, visible hostile monsters/threat colours, known inventory labels,
and recent messages. No hidden monster HP, hidden locations, engine RNG, or map
spoilers enter the policy. Collections are JSON objects with numeric-string keys,
not JSON arrays. The pilot has no recurrent memory and cannot solve general
invisibility tactics. Messages contain UI markup/noise; models should not assume
clean prose. Inventory letters are Crawl's category-specific selectors.

The Lua adapter is inserted into a snapshot of the canonical RC, reuses its local
visible-map scanner, and suppresses `ready()` automation between learner actions.
It serializes `BOT` as well as the production save globals. It uses character
dumps for structured transport, not fragile map-screen parsing. Console entry
requires a confirmed interpreter banner and a per-decision acknowledgement.
Sequence numbers reject redrawn historical readiness messages. A confirmed
read-only console probe handles commands that consume no turn and do not call
`ready()` again. Unexpected prompts/errors stop the trial, not count as deaths.

## Crucial fidelity limitation

**A save-loaded encounter is not yet proven equivalent to uninterrupted play.**
The fresh, stepped seed-3 trajectory reproduces the original Eustachio death.
But reloading the first-contact save changes the next monster action and outcome.
Repeated resets of that save agree with one another. Preserving `BOT` alone did
not fix the discrepancy; the engine's full save/load fidelity needs investigation.

Therefore these cases are labelled **save-loaded variants**, not exact historical
replays. The later critical case still has a reproducibly losing baseline, making
it useful for a small controlled experiment. Do not promote a policy based on
checkpoint success alone: replay the uninterrupted seed and then held-out seeds.

## Outcomes and learning

`experiment.py` compares RC, Tab, and a hand-written adjacent-berserk/Tab policy,
then performs a small tabular Q-learning run and two greedy evaluations. Q-learning
updates after each environment transition; this is online RL against a local
simulator, **not offline RL from a fixed dataset**. The transition dataset is a
foundation for subsequent offline work.

The Q policy chooses wait/Tab/one-step retreat/berserk using coarse HP, crowd,
distance and status buckets. It has epsilon-greedy exploration, alpha 0.3 and
discount 0.98; Python sampling seed is 0. This is only a plumbing smoke test.
Macro duration is logged but the current discount is per decision, not per turn.

- Death: observed engine death message; not a timeout.
- Safe recovery: no visible hostiles, engine says safe, full HP, no active status,
  poison or fire, sustained for at least 10 game turns. This is an observable
  safety proxy and can include escape; it does not assert Eustachio was killed.
- No-turn stall: eight consecutive decisions without turn advancement.
- Budget truncated: decision limit reached without another terminal condition.
- Harness error: unexpected prompt, timeout, engine error, or adapter failure.

Rewards: death -100, safe recovery +100, -0.1 per decision, -2 for a no-turn action,
and a small HP-fraction difference term. No kill reward encourages ignoring
lingering hazards. These reward weights and the coarse abstraction are provisional.
Current actions exclude consumable selection and targeted wands/throwing.

Artifacts include `run.json`, `transitions.jsonl`, `rewards.jsonl`, `result.json`,
`results.json`, `q.json`, terminal logs, and morgues. Early exploratory workers
predate `run.json`; their case metadata and frozen trial RC remain available.
Large artifacts are local and git-ignored. Small evidence summaries are tracked.
Identical reset evaluations test repeatability, **not generalization**.

Next: fix or characterize save/load divergence; capture earlier losing decisions
with an uninterrupted replay fallback; expose consumables and safe action masks;
expand to multiple encounters with held-out cases before scaling training.

## First pilot results (2026-09-08)

Three local cases were captured: first contact (turn 3506, 56/56 HP), return after
teleport (3528, 42/56), and surrounded/critical (3541, 35/56). Two experiments
produced **24 episodes and 1,009 transitions**. See
[tracked evidence](evidence/initial-pilots.json) for hashes and worker paths.

On the critical save-loaded variant, RC baseline died in 3 decisions in both
repeats, and Tab also died in 3. The hand-written adjacent-berserk/Tab policy
recovered safely in 78 decisions. Q-learning found one safe recovery in 8
exploratory training episodes, but both subsequent greedy evaluations died.
The earlier return case's four training episodes and both greedy evaluations
also died. **No reliable learned improvement has been demonstrated.**

Repeatability checks compared normalized observations, not just final outcomes:
100 first-contact baseline decisions matched across resets; all 3 critical
baseline decisions matched. Median reset time was approximately 5.6 seconds in
the return pilot and 9.0 seconds in the critical pilot. These are local measured
times, not a throughput guarantee. No full five-seed benchmark was run here.

The RC-baseline return trials exhausted 180 decisions while continuing normal
play; they were not relabelled victories merely because the player remained
alive. Recorded death `final_turn` is the last observed decision boundary, not
necessarily the morgue's terminal turn. All worker artifacts remain local.
