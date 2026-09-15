# Local vision and ogre awareness screen

2026-09-15. Implementation: `branches/vision-ogre-v1`, integrating the validated
vision-awareness task with the existing `ogre-metrics-v2` baseline dynamics.

## Runs

1. Continue the seed-0 no-ogre LOS-wake model from 30,015,488 to 100M decisions.
   Original weights, optimizer, live environments, and RNG states are preserved.
   Suite: `learning-runs/vision24-512-los-awareness-100m`.
2. Fresh seed-0 30M training: `ogre2_wake_radius`.
3. Fresh seed-0 30M training: `ogre2_wake_los`.

The two ogre runs are sequential in `learning-runs/vision-ogre2-wake-screen-30m`.
Their queue waits for successful completion of the no-ogre suite; it stops if the
predecessor fails or stops early. Logs and launch metadata are in `results/`.
Approximate compute: 6–7 minutes for the additional 70M no-ogre decisions;
3–4 minutes per ogre run including evaluation and startup. Actual training time
is recorded separately from evaluations and setup. Each suite has a 2 GiB cap,
a 5 GiB free-space reserve, and bounded checkpoint retention.

## Fixed configuration

- 256 ordinary training layouts, the existing 32 validation layouts × 32 episodes.
- 24 required ordinary enemies, 2 optional ogres, 512 turns, no healing or stairs.
- Local enemy records only; native wall-blocked player LOS cropped to radius four.
- Six-tile monster wake radius. Radius arm ignores intervening walls; LOS arm
  additionally requires native LOS from the monster to the player. This applies
  to regular enemies and ogres. Already-awake monsters retain existing pursuit.
- Ogre HP 48; speed 5 (regular speed normally 10), damage 24, to-hit 30, bypass 25.
  Existing energy scheduling gives one action every other player turn. On waking,
  energy resets to 70, so the ogre's first action follows on the next turn.
- Ogre spawn Chebyshev distance at least 12 from the player. Separate spawn RNG
  preserves ordinary-enemy/player initial placements across zero/two-ogre tasks.
- Kill ordinary enemy +1, clear all 24 +3, death −1, turn −0.001,
  first-seen floor +0.002. Ogre kills give no reward and are not needed to clear.
- Same PPO settings and 502-input, two-layer 128-unit policy as the vision runs.
  Neither ogre training run initializes from the no-ogre model.

## Observations and diagnostics

Visible ogres use discovery-ordered enemy records with relative position, current
HP, distinct type code 1.2, and presence. Hidden records are zeroed; no live
information persists outside sight. The optional-role label remains off, and no
extra awake, speed, damage, energy-phase or max-HP channels are added. These
feature combinations are compile-time rejected until separately integrated.

Original observation offsets and visibility channels are preserved. Outputs
8–10 and 12 continue to describe **required ordinary enemies**, so unseen enemies
remaining at timeout are not inflated by surviving optional ogres. Ogre metrics
are separate: kills, damage, actions, adjacent turns, living/awake counts,
ogre-caused deaths, wake events, turns near/adjacent to awake ogres, encounters,
and visibility. Evaluation accumulates wake/exposure events across the episode,
including the final transition before auto-reset. Report both unconditional
clear-with-ogres-alive rate and the fraction conditional on clearing.

Native diagnostic slots: 14 kills, 15 damage, 16 actions, 17 adjacent turns,
18 awake survivors, 19 survivors, 20 fatal blow, 21 wake events, 22 awake-adjacent
turn, 23 awake-within-three turn, 24 encountered ogres, 25 currently visible ogres.

## Validation

`results/vision-ogre-validation.txt`: three end-to-end smoke jobs passed; native
checks exercise spawn constraints, energy timing, optional kills/rewards,
clearing with surviving ogres, wake occlusion and knowledge leaks. Each of the
zero-ogre and two ogre variants passed 8,400 CPU/CUDA world steps, reward accounting,
active masking, and diagnostic invariants. An additional 8,400 world steps of
zero-ogre replay exactly matched the original LOS-wake task's observations,
action masks, rewards, and original diagnostics.

Run/resume the queued experiment:

```sh
gpu-d1/.venv/bin/python gpu-d1/branches/vision-ogre-v1/scripts/queue_after.py \
  --after-suite gpu-d1/learning-runs/vision24-512-los-awareness-100m \
  --output gpu-d1/learning-runs/vision-ogre2-wake-screen-30m \
  --steps 30000000 --seeds 0
```

This is a single-seed screening comparison. It changes enemy wake mechanics,
not player observation features. The validation panel is reused development data,
not a fresh final test set. Improvements or regressions need training-seed repeats
before a robust algorithmic claim.
