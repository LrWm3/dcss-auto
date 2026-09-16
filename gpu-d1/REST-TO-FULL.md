# Rest-to-full versus repeated waiting

Purpose: test whether choosing one recovery action is easier to learn than
sustaining repeated wait decisions. Two fresh seed-0 models train to 10M policy
decisions, with a 2048-policy-decision episode budget in both arms.

- Wait-only: the existing eight movement/attack directions plus primitive wait.
- Rest-enabled: those actions plus rest to full (action 9).

Both use the exact-D4 policy, one-third clumped placement, 24 ordinary enemies,
256 training layouts, 32 validation layouts, 15x15 wall-blocked vision, LOS wake,
and seen-floor progress input. No ogres, frontier-travel action, or targeted
curriculum. Rewards stay +1 kill, +3 clear, -4 death, +0.002 newly seen floor,
and -0.001 per physical turn. PPO settings remain unchanged.

## Action and clock semantics

Rest is available only when HP is below its maximum and no living enemy is
visible. A visible sleeping enemy also disables it. Native waiting is executed
repeatedly until HP is full, an enemy is sighted during a turn, or the episode
ends. Enemies, regeneration, energy, LOS, and rewards advance normally. This is
not instantaneous healing and does not pause enemies.

The primitive rewards are summed into one transition. That transition consumes
one model decision regardless of the number of physical turns. PPO discounting
is per decision, as requested; no extra discount is applied inside the macro.
Thus this comparison tests the combined learning and decision-efficiency benefit
of the action, not merely a change in its name. Physical-turn penalties remain.

Timeout uses 2048 decisions, and the existing clock input now represents elapsed
decisions / 2048. Physical turns are recorded separately and may exceed 2048.
A rest chosen on the last allowed decision can finish or be interrupted before
the decision timeout is applied. A native death or clear takes precedence.
An invalid direct call falls back to one wait; normal policy masks prevent it.

## Fairness and measurements

Both policies have ten output slots, with rest permanently masked in the control.
This gives identical initial model weights, including body, critic, and action
head, rather than changing their initialization through a different output size.
The rest action maps to itself under all eight D4 transformations.

Sampled and greedy validation run at initialization, 1M, 3M, 5M, and 10M, using
1,024 episodes on the same held-out validation maps. Ordinary test maps are unused.
Report clears, deaths, decision timeouts, physical turns, policy decisions, and
training time. Additional counters report rest activations, physical rest turns,
full-health completions, sighting interruptions, invalid uses, net HP gained,
primitive waits, safe low-HP waits, and recovery opportunities.

One seed is an initial screen; any apparent benefit needs replication. No claim
of equal physical simulation work is appropriate: a rest decision can perform
many simulator turns. Both arms have the same decision budget, by design.

## Verification and execution

`branches/vision15-rest-full-v1/scripts/assets.py` compiles the train/validation
libraries and native tests. `preflight.py` verifies exact simulator-state and
reward equivalence to repeated waits, full-HP/visible-sleeper masks, interruption
on an approaching enemy, decision timeout, physical turns beyond 2048, inactive
world preservation, D4 action invariance, identical initial weights, and PPO
update/resume for both arms. The large native test runs in its own process so its
CUDA stack allocation is released before training smoke tests.

`run_experiment.py` runs the two jobs sequentially and can resume them. Generated
maps, binaries, checkpoints and logs stay in ignored `learning-runs/rest-full-assets`
and `learning-runs/vision15-rest-full`. Retention uses a 2 GiB suite budget and
10 GiB free-space reserve. Compact snapshots accompany live resume checkpoints.

The earlier choice-practice queue was stopped at the user's request. Its active
sleep-practice worker saved at an update boundary; completed target/control
results and partial training checkpoints remain available.
