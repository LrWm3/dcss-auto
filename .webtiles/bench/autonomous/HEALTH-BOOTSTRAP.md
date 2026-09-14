# Health-aware bootstrap experiment

`run_health_bootstrap.py` opts into `DCSS_REPRESENTATION=spatial-v6` and
`DCSS_HEALTH_FEATURES=1`. The feature version becomes
`general-features-v6-spatial-entities-health-v1`. Normal legacy V6 entry points
remain unchanged. Loading the wrong feature version fails explicitly.

The new global fields are health availability, full health, fractional HP deficit,
and scaled absolute HP deficit. They describe the observation; they do not force
the policy to wait or move. They are inserted before history, so existing history
masking retains its intended layout. Explicit migration adds zero-weight columns
to the policy and critic global encoders, retaining the old model's initial
function. A projection-equivalence check runs during migration.

Training sampling now reserves a few examples per action kind and samples the
rest naturally, rather than equalizing MOVE and WAIT counts. No held-out
observations enter fitting. The original run also oversampled healing boundaries;
future runs no longer do that. The teacher's immediate-rest preference is bootstrap
supervision, not a universal tactical rule.

The bounded experiment performs one 12-epoch fit, then reports the paired
full-health/injured input checks as diagnostics only. Immediate agreement with the
teacher no longer determines acceptance.

The acceptance precheck restores five actual saved states and runs up to 256
policy decisions each. Brief waiting and repositioning while injured are allowed.
Healing, MP recovery, new positions, exploration, score gains, inventory changes,
and cleared impairments count as activity for this diagnostic only, not as
training rewards. A case stalls after 128 consecutive safe, unthreatened decisions
with no observed progress. Repeated visits to the same tiles cannot reset this
counter. Combat/impairment time is excluded from safe inactivity. At least four
cases must show activity without stalling; errors fail the check. This establishes
liveness, not tactical quality or survival. Terminal outcomes are recorded.

Passing launches paired starting-policy/candidate games
on five fresh reserved seeds, each capped at 2,000 total decisions. It does not
promote a champion or start RL.

The smoke run fits only 16 rows for one epoch. `smoke_complete` means the machinery
executed, not that the policy passed the behavioral gate. The first smoke did not
pass that gate, as recorded in its output.

Historical run reports retain their original gate decisions. Re-evaluate an
existing checkpoint without retraining using `check_health_rollouts.py --model
... --source ... --output ...`; results go to a new directory. The first such
review, `v6-health-repair-03/rollout-review-01`, found all five cases eventually
stalled: four immediately waited 128 times, and one briefly moved/fought before
waiting 128 consecutive times without progress. No policy was promoted.

Production-sized bounded run:

```bash
.webtiles/bench/tactical/.rl-venv/bin/python \
  .webtiles/bench/autonomous/run_health_bootstrap.py \
  --source .webtiles/bench/autonomous/artifacts/v6-bootstrap-repair-02 \
  --replay-run .webtiles/bench/autonomous/artifacts/foundation-general-training-v6 \
  --initial .webtiles/bench/autonomous/artifacts/v6-fit-probe-01/warm.pt \
  --output .webtiles/bench/autonomous/artifacts/v6-health-repair-03
```

Inspect `status.json`, `training.json`, `health_check.json`, and (if reached)
`baseline/results.json` and `candidate/results.json`. The existing disk-space
guard applies. Completed fitting/episodes are reused on restart; terminal review
states require a new experiment rather than silently retraining.
