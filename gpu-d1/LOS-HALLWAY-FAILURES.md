# Hallway retreat: regression and sampled deaths

Examines the privileged-pursuit arms of `results/los-hallway-retreat.json`.
The retreat itself uses observed terrain and visible enemies only. No policy or
simulator changes were made for this audit.

Across 1,024 episodes, retreat reduced deaths from 66 to 31: 36 former deaths
became clears, and one former clear became a death. **30 of the remaining 31
deaths never started a retreat.** 25 deaths occurred within 40 physical turns;
27 within 100. These counts describe the full panel, not just the sample.

## The one regression: episode 863, map 72581

Control cleared all 24 enemies in 400 physical turns. Retreat died with 16 kills
at turn 289. The trajectories first diverged at decision 96.

All three retreats reached their targets (15, 18, and 5 movement steps).
There were no blocked retreats and no hallway waiting actions. On the third
arrival, the player had full health, 18/18, and only one adjacent enemy. It
remained at (24,24), attacked continuously, killed the first enemy, and then
fought the next enemy alone. The second enemy was regular kind 4: 12 initial
HP, speed 12, base damage 5 (not an ogre).

At the start of that second fight, the player still had 18 HP. Its subsequent
HP values were 12, 8, 5, 2, 3, 2, 0. The enemy had 3 HP immediately before the
fatal turn. The hallway successfully prevented simultaneous adjacent enemies;
it did not guarantee winning the resulting one-on-one fight. There was no
rest opportunity during this fight because an enemy remained visible.

The control also came close to death later: it reached 2 HP before eventually
clearing. Different movement and combat sequences consume randomness differently,
so this matched outcome flip does **not** establish that the retreat position
was intrinsically worse. It establishes that this policy still permits a
full-health one-on-one loss after reaching the intended defensive position.

## Five other deaths

Selected deliberately to cover very early, intermediate, and late deaths;
this is a diagnostic sample, not a random sample for estimating proportions.
All five reproduced the control's actions, positions, HP, and kills exactly.

| Episode | Map | Death turn | Kills | Observed failure |
|---|---|---:|---:|---|
| 624 | 66384 | 10 | 1 | Six enemies become adjacent during the opening fight. No known exact hallway. |
| 48 | 66384 | 20 | 2 | Multiple-enemy fight drains HP; dies finishing the remaining enemy. No known exact hallway. |
| 112 | 66384 | 133 | 9 | Three enemies converge; dies fighting two survivors. No known exact hallway. |
| 332 | 65772 | 261 | 17 | Knows 58 reachable hallway tiles during the final fight, but none passes the first-step-away condition. |
| 870 | 64106 | 77 | 6 | Knows 22 reachable hallway tiles; destination/first-step direction rules reject them. |

For episode 332, 49 of the 58 known hallway tiles lie away from the enemy
centroid at decisions 206–214, but the deterministic shortest paths all start
with a step that is not strictly away. Later, 41 destinations pass, still with
zero accepted first steps. The policy does not search alternative first steps
or longer detours. This explains why “no qualifying hallway” does not always
mean “no hallway known.” It does not prove any rejected route was safe.

In the first three sampled cases, the exact six-wall/two-opposite-floor pattern
is absent from remembered terrain whenever retreat is considered. Some terrain
is narrow or partially protective, but the current rule does not recognize
those as destinations. This is consistent with its deliberately strict definition.

## Interpretation

Most remaining deaths occur without the new tactic ever activating. The sample
identifies two limitations: requiring an exact hallway pattern, and requiring
both the destination and the selected route's first step to point away from
the enemy centroid. The regression identifies a third: sequential combat can
still be lethal, and the policy has no low-HP disengagement rule.

This audit does not establish which deaths are avoidable. A useful next
comparison would relax the first-step restriction while keeping known terrain,
enemy blocking, rest, and the destination rule unchanged; separately, one could
test less restrictive defensive destinations. Neither change was made here.

## Reproduction

Run `gpu-d1/.venv/bin/python gpu-d1/diagnostics/seek-destroy-los/inspect_failures.py`.
It initializes the original 1,024-world batch with seed 900000, then freezes
unselected worlds, preserving each selected world's RNG stream and map index.
Both arms reproduce saved terminal clear/kill/turn outcomes exactly. The script
records pre-action observed grids, visible enemy HP/type/sleep state, retreat
state/events, known hallway coordinates, rejection counts, and post-action HP.
Terminal observations auto-reset, so snapshots use pre-action observations.

Trace artifact: `results/los-hallway-failure-traces.json` (six episodes, both arms).
Grid symbols: `@` player, `A` visible awake enemy, `s` visible sleeping enemy,
`#` remembered wall, `.` remembered floor, `?` unknown. No hidden terrain is
used for the hallway diagnosis.
