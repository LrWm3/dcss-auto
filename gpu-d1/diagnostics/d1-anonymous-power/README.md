# Calibrated anonymous-enemy power experiment

Calibration and preflight complete, 2026-09-17. First training run: seed 0,
5M additional policy decisions, checkpoints at 0.5M/1M/3M/5M.

## Calibration

No learned policy was used to select the distribution. We measured 2800 cases:
player maximum HP {10,12,18,24,30}, player damage cap {2,3,4,5,6}, enemy HP
{6,10,16,24,36,52,72}, enemy damage cap {2,4,6,8,10,12,16,20}, and half/full
starting HP. Each case has 2048 independent combat rolls (5,734,400 duels).

The calibrated event is surviving an adjacent, awake, one-on-one fight while
attacking every turn. Player hit probability is 80%; successful player damage
and raw enemy damage are uniform integers from 1 through their respective caps.
Production evasion, armor, shield, and 0.23 HP/turn regeneration remain in force.
All enemies act at speed10 and share accuracy19/bypass15. No enemy identity or
speed observation is supplied; visible HP/maxHP/damage/sleep remain observable.

The optimized duel evaluator matches 512 full-simulator fights exactly, including
outcome, turns, remaining HP and damage; another 8192 fights match CPU and CUDA.
Initial energy is70. At common speed10, energy70–79 produces the same one-attack
per-turn timing. Calibration is conditional fight risk, not predicted floor risk.

The old player range (12/18/24HP, damage caps3/4/5) had only three enemies meeting
the crossover criterion (at least30% death risk for the weakest player, at most2%
for the strongest). We chose the measured broader range **10/18/30HP and damage
caps2/4/6**, which supports separate training and held-out enemy catalogues.

After selection, all six training enemies were independently confirmed at all
nine player-strength pairs and half/full HP, with 8192 fresh rolls per cell
(884,736 duels). The following are **full-health fight death percentages**:

| Enemy HP / damage cap | Role | Player10HP/cap2 | Player18HP/cap4 | Player30HP/cap6 |
| --- | --- | ---: | ---: | ---: |
| 10 / 4 | Weak | 0.11% | 0% | 0% |
| 6 / 4 | Weak | 0.02% | 0% | 0% |
| 36 / 6 | Crossover | 59.42% | 3.25% | 0% |
| 6 / 20 | Crossover | 62.35% | 14.14% | 1.34% |
| 24 / 10 | Crossover | 88.71% | 24.65% | 0.62% |
| 24 / 20 | Dangerous | 99.69% | 85.75% | 37.65% |

Role labels exist only in experiment metadata. The model does not see them.
Zero observed deaths does not establish zero risk. Full confirmation covers
every player HP/damage combination, not just the three diagonal examples above.
“Weak” describes full-health risk; an injured player may still be vulnerable.

## Chosen first training distribution

- Uniformly draw one of nine player HP/damage pairs at each reset.
- Each of 24 enemies independently draws one of the six training templates.
  This gives 1/3 weak, 1/2 crossover, and 1/6 universally dangerous enemies in
  expectation. The enemy catalogue is identical at every player strength.
- No hidden type-specific speed, accuracy, or attack behavior remains. The old
  kind observation field is zero; it is retained only to preserve checkpoint
  tensor shapes. Enemy slot index does not determine stats.
- Keep 256 training layouts, one-third clumped placement, 15x15 wall-blocking LOS,
  six-tile LOS wake, REST, frontier/stair guidance, three working stairs, and the
  2048-physical-turn deadline.
- Reward stays +1 on descending and -0.00001 per physical turn. No kill reward,
  exploration reward, threat labels, new demonstrations, or practice resets.

This intentionally makes dangerous encounters appreciably more common than
before. In expectation a floor has four universally dangerous enemies. It is a
first pressure screen, not a claim this is an optimal final difficulty mix.

## Training and evaluation

Start from the same frozen broader D1 source as the earlier stat experiment:
`learning-runs/d1-stairs-survival-broad/targeted/checkpoints/3000320.pt`.
Existing new stat columns start at zero as before. The baseline is evaluated
under the **same anonymous, common-speed mechanics** before any updates, so the
observation/mechanics change is not mistaken for training improvement.

Reuse the audited PPO update: gamma1, GAE0.95, LR0.0003, four epochs, clip0.8–1.2,
value coefficient0.25, gradient clip0.5, no entropy bonus, 512 worlds x64 steps.
Navigation/ordinary replay anchors remain, with identity removed from replay
inputs. Ordinary replay targets use the frozen source under anonymous inputs.
The old navigation teacher's navigation targets are retained. Neither anchor
imitates the source on new dangerous rollout states.

Evaluate sampled and greedy behavior at 0/0.5M/1M/3M/5M on32 validation layouts.
Selection uses mean validation exits across nine training stat pairs and an
ordinary-stat anonymous profile. The source is eligible. Afterwards evaluate
the source, selected checkpoint, and final checkpoint on100 held-out layouts:

- Seen player/enemy catalogue combinations.
- Six unseen enemy templates selected by matching calibrated risk profiles,
  disjoint from the training catalogue.
- Unseen player HP14/24 with each trained damage cap2/4/6.
- Ordinary-stat retention under anonymous/common-speed mechanics.

Report exits/deaths/timeouts, physical turns, discovery, incoming damage,
surviving enemy fraction on exit, training seconds, and physical training turns.
Train/test layouts are disjoint but reused from previous experiments. This is
one training seed; small differences do not establish a reliable improvement.

The objective still rewards leaving, not necessary fighting. Even a safer
fight need not be worth taking when a free bypass exists. Success here means
better survival/exit behavior across strength conditions; it is not by itself
proof of a power-dependent optimal fight/avoid strategy reversal.

## Checks, storage, and reproduction

Preflight passes 1280 paired CPU/CUDA decisions, hidden-enemy non-leakage,
REST/deadline/three-stair semantics, zero identity fields, inactive enemy slots,
uniform player-profile sampling, independent per-enemy template sampling, and
fresh confirmation of weak/crossover/dangerous risk criteria.

New native behavior is behind `ANONYMOUS_POWER`; existing builds keep their old
identity, speed, profile-sampling, and monster-stat behavior. The standalone
diagnostic includes the existing simulator rather than copying its combat rules.

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-anonymous-power/calibrate.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-anonymous-power/preflight.py
gpu-d1/.venv/bin/python gpu-d1/diagnostics/d1-anonymous-power/run.py
```

Do not regenerate the catalogue during an active run. The launch manifest and
preflight pin source/catalogue hashes. All binaries, checkpoints, logs, and raw
run state stay under ignored `learning-runs/d1-anonymous-power/`, bounded by a
4GiB artifact budget and10GiB free-space floor. Calibration/confirmation JSONs
under `results/` and the selected `distribution.json` are tracked.
