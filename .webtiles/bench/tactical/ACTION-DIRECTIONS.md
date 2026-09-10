# Explicit directional imitation — 2026-09-10

Run: `artifacts/action-direction-v1`, using unchanged cases from `action-broader-v1`.
Training uses the same 8,608 training-only states/labels. No new encounter mining,
validation-label fitting, PPO fine-tuning, or production deployment.

## Results

| Frozen policy | Training recovered / died / timed out | Validation recovered / died / timed out |
| --- | --- | --- |
| Previous broader hashed actor | 19 / 12 / 5 | 6 / 2 / 0 |
| Earlier reference correction actor | 22 / 13 / 1 | 6 / 2 / 0 |
| Directional scorer, original sampler | 23 / 8 / 5 | Not evaluated |
| Directional scorer, capped sampler | 23 / 8 / 5 | **8 / 0 / 0** |
| Pursuit teacher | 23 / 8 / 5 | 8 / 0 / 0 |

Earlier-model/teacher results come from identical-case prior runs. Both new
directional models match the teacher's training outcome counts. The predetermined
capped model now recovers all eight validation variants, including both water
moccasins and both ribbon worms. It does **not** outperform the teacher. The
eight variants are four families on one previously studied validation seed, so
this is a useful imitation result, not a broad generalization claim.

Both new models had zero adjacent-enemy waits and zero waits when the teacher
would act in training; the capped model also had zero of both in validation.
Its training had 354 adjacent-enemy decisions, versus 352 for the teacher/original
sampler model; validation had 72. Equal outcome counts do not mean identical
action sequences. The cap did not improve outcome counts relative to the original
sampler in this training comparison; its benefit here is a verified bound on
rare-example oversampling, not a demonstrated win-rate gain.

All 80 episodes passed transition/outcome audits: 54 recoveries, 16 deaths and
10 budget truncations across both training replays and capped validation. No
harness errors or no-turn stalls. 207 Python tests plus 13 embedded Lua checks
passed. No production controller was replaced.
An additional checkpoint audit recomputed all **6,000 model decisions** from
recorded states/masks and verified they matched the executed actions in all 80
episodes; saved checkpoint hashes matched their fit records.

Next: integrate the shared scorer into action-level RL with an explicit imitation
constraint and fixed training-only comparisons, targeting cases the teacher fails.
The old unconstrained fine-tuning regressed; do not assume a better imitation
initialization by itself prevents that failure. Adding richer tactical fields or
memory may be necessary beyond pursuit imitation.

## Representation and scope

`direction_policy.py` replaces the large hashed observation actor with a small
shared scorer. Each of the ten actions receives 32 numerical features: 12 global
player/threat fields and 20 action-relative fields. The same [64,64] tanh network
scores every action; unavailable actions are masked before argmax.

Global fields cover HP/max HP, enemy count, safe/unseen/confused/berserk/cooldown,
AC, EV, XL and poison. Action-relative fields include direction, wait/berserk flag,
terrain and cloud/occupancy/disturbance flags, a direct hostile target and threat,
enemy distance/alignment/adjacency, local maneuvering space, and whether/at what
length known-map routes to visible enemies begin with that action.

**Known-map planning is supplied as features**, not learned from scratch. The
existing `paths` helper computes routes from observable geometry. These route
features encode substantial structure useful to the pursuit teacher. They are
not a teacher-selected action, hidden enemy position, seed, or outcome label.
The model still chooses each action, but better pursuit imitation is not evidence
of discovering superior tactics or learning pathfinding unaided.

This is a narrower current-state representation, not a richer general Crawl model:
it omits the old four-frame memory and most detailed gear/monster attributes.
The raw event observations remain intact. Its checkpoint is a standalone PyTorch
scorer, not directly loadable by the old MaskablePPO trainer without integration.
The same underlying ActionEnv still provides masks, action transport, logging and
recovery boundaries; its hashed observations are computed but discarded here.

## Controlled sampler comparison

Two identical randomly initialized directional scorers (seed 42) use the same
dataset, 30 epochs, batch 128, Adam .001 and gradient clipping .5. Only sampling
differs:

- Original stratified/disagreement weights.
- Those weights capped so **no individual example exceeds four times uniform
  sampling probability**, with excess redistributed among uncapped examples.

The eight threatened-wait labels had 20% total sampling mass. Capping reduces that
to 0.3717%; directions receive 71.9386% and other waits 27.6897%. Probabilities
still sum to one and every example retains positive mass. Unit tests cover the
hard cap, normalization, degenerate inputs, direction-specific fields and masking.

All training examples are rebuilt from audited raw training trajectories and
relabelled with the unchanged pursuit teacher. Source data checksums and seed split
are checked. Both models fit all 8,608 labels correctly, including all three groups.

Both frozen models are replayed on all 36 training variants. Only the **capped**
model is evaluated on the eight validation variants, chosen in the manifest before
training rather than selected from training/validation results. No final test use.
Comparisons to the older hashed actor also change architecture and fit budget;
they do not isolate the causal effect of representation alone.

## Reproduce

Use the existing RL Python environment and parent artifacts. Output must be new.

```sh
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/train_direction_pilot.py --parent .webtiles/bench/tactical/artifacts/action-broader-v1 --output /absolute/new/direction-run
.webtiles/bench/tactical/.rl-venv/bin/python .webtiles/bench/tactical/audit_action_episodes.py /absolute/new/direction-run
.webtiles/bench/tactical/.rl-venv/bin/python -m unittest discover -s .webtiles/bench/tactical -p 'test_*.py'
```
