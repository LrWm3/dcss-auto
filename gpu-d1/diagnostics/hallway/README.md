# One-square hallway retreat test

2026-09-16. Read-only diagnostic of the ordinary-trained and one-third-clumped
seed-0 30M checkpoints. No retraining, reward changes or extra policy inputs.

```text
xxx
ggg
x@x
x.x
xxx
```

The player begins adjacent to all three enemies. Stepping onto the dot puts
all three at distance two; that destination has only one walkable neighbor.
Pursuit therefore brings one enemy at a time into contact. Native assertions
check this geometry, and all three enemies must be visible initially. The same
native ray definition as the corpus compiler supplies LOS on synthetic maps.

Test all four rotations, player HP 6/12/18, and two existing enemy types:
weak = kind 0, 8 HP, damage proxy 3, speed 10; tough = kind 3, 16 HP, damage
proxy 5, speed 10. All start awake with normal randomized 70..79 energy.
Player defenses and regeneration remain unchanged. Each condition uses 512
combat RNG seeds, shared across policies, controls and rotations. Rotation
replicates are not independent combat seeds. Sampled actions use seed 900000.

Set the episode to turn 256/2048 with 21 enemies already defeated. The three
remaining enemies are the encounter; killing them completes the floor. Only
five floor squares have been seen (seen-floor input = 5/1024). This synthetic,
fully local situation is outside the usual map distribution and is a local
competence test, not an estimate of ordinary-map clear rate. The model is not
shown the number of remaining enemies. Distant disconnected padding floor
allows the original terminal auto-reset to run; it has no live test enemies,
is never visible, and cannot be reached from the encounter.

Run from repository root:

```sh
gpu-d1/.venv/bin/python gpu-d1/diagnostics/hallway/run.py
```

Controls: hold position and attack the lowest-HP adjacent enemy, or retreat
once and then use that same fighting rule. Wait only if no enemy is adjacent.
Natural-policy arms use the unmodified policy. Additional arms force only the
first action (retreat or the control's attack) and then restore policy control.
Every arm has a 256-action diagnostic cap; all episodes resolved without hitting
it. The policy's original 2048-turn observation/deadline remains unchanged.
First-action probabilities and greedy retreat decisions are recorded separately.

## Results

Win percentages averaged equally over four rotations:

| Enemy type | Player HP | Hold and fight | Retreat then fight | Original policy | Clump-trained policy |
|---|---:|---:|---:|---:|---:|
| Weak | 6 | 71.3% | 99.2% | 99.1% | 97.0% |
| Weak | 12 | 97.1% | 100% | 100% | 99.8% |
| Weak | 18 | 100% | 100% | 100% | 100% |
| Tough | 6 | 5.1% | 61.3% | 51.0% | 58.3% |
| Tough | 12 | 32.8% | 93.9% | 92.2% | 93.3% |
| Tough | 18 | 69.3% | 99.0% | 99.0% | 98.7% |

Tough enemies at 12 HP provide a strong example of likely death while holding
position and likely survival after retreat. Both natural policies approach the
retreat control's survival, though neither always retreats immediately:

| Rotation | Original first-retreat probability | Clump-trained first-retreat probability |
|---|---:|---:|
| As drawn, retreat south | 87.2% | 60.4% |
| Retreat west | 54.7% | 99.6% |
| Retreat north | 99.6% | 92.4% |
| Retreat east | 56.9% | 98.2% |

Greedy first action is retreat in all four of those conditions. Across all
24 conditions, it is retreat in 22 for the original and 21 for clump-trained.
The original fails this greedy criterion at 6 HP/tough enemies when retreat is
west or east. Clump-trained fails it against weak enemies when retreat is south,
at each tested HP. Thus neither passes an all-cases immediate-retreat criterion.
No universal pass threshold was imposed after observing results.

For tough enemies at 12 HP, forcing a first attack and then returning control
to the policies still yields 89.6% original / 91.2% clump-trained wins, versus
94.0% / 93.9% when forcing retreat first. The large control gap primarily tests
remaining in the exposed position, not a claim that every one-turn delay is
fatal. At 6 HP, first-attack wins are 44.9% / 50.5%, versus 61.3% / 61.3% with
first retreat, making the first decision more consequential but still not
sufficient to guarantee survival.

Both policies demonstrate this local retreat behavior. Directional sensitivity
and occasional delay remain, and the mixed policy is not uniformly better.
This helps distinguish an ability to use an obvious local chokepoint from
reliably recognizing retreat opportunities in larger, uncertain encounters.

Artifacts: `results/hallway-retreat.json` contains all per-condition outcomes,
first-action probabilities, checkpoint/source hashes and runtime. Maps and shared
library are regenerated under ignored `build/`; no persistent trajectories.
