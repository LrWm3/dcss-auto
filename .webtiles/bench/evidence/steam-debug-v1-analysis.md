# Steam encounter: single-decision replay

Seed17908030050512890810, CodexSteamDebug1, codex-bench4.
Diagnostic commit6427dfd62cefdfbb155090bf6ebf39c931d72b56; snapshot SHA
eae873eb0f8e17fdc0e2c3667a62da938148bade2125e712eca394318f942a5e.
Combat settings unchanged from wand-mesmerism-full-v1; steam_debug=true only.
Paused upon first visible D:6 steam dragon, before ready's tactical decision,
turn5877 HP58/71. Each subsequent ready decision was individually authorized
and inspected; no manually selected gameplay moves, items or abilities.
This is a diagnostic replay, not an autonomous benchmark measurement.

## Result and confidence

Reproduced original death: turn5913, XL8, score1498, -9/71HP, orc priest
smite13, priest almost dead. Earlier milestones and the3HP steam event5887
also match. All44 controller decisions inspected. Seven rejected Tabs took
no turn (not eight: the final fatal action also does not increment turns()).
No actual Confusion status was present in any snapshot.

Full notes are in steam-debug-v1-CodexSteamDebug1.txt. TRACE timestamps in the
left column are the time the buffered report was printed; embedded turn= is
the actual snapshot turn. Before-decision phase is the previous observed phase;
encounter-transition EVENT notes show updates inside the decision. Decision44
died before its buffered TRACE report could be printed; its gameplay EVENT
notes and death record remain. Reports omitted no adjacent-tile diagnostics.

## Every decision

| Decision | Starting turn | Starting HP | Action and outcome |
| --- | --- | --- | --- |
| 1 | 5877 | 58 | Trog's Hand; unseen attacker hits for no damage; HP59 |
| 2 | 5878 | 59 | Position south into narrower corridor; HP60 |
| 3 | 5879 | 60 | Tab tries north, attacks something unseen; HP62 |
| 4 | 5880 | 62 | Tab north attacks unseen foe; steam breath hits; HP50 |
| 5 | 5881 | 50 | Unsafe-square handler waits inside steam: all adjacent steps forbidden; HP51 |
| 6 | 5882 | 51 | Tab attacks adjacent dragon; HP53 |
| 7 | 5883 | 53 | Tab misses dragon; HP53 |
| 8 | 5884 | 53 | Tab misses dragon; HP55 |
| 9 | 5885 | 55 | Tab severely wounds dragon; bite/breath reduce HP33 |
| 10 | 5886 | 33 | Disengage state but Tab melee; steam and priest smite reduce HP10 |
| 11 | 5887 | 10 | Tab ineffective melee; breath reduces HP3 |
| 12 | 5888 | 3 | Tab kills dragon; HP4 |
| 13 | 5889 | 4 | Tab attacks marrowcuda; HP6 |
| 14 | 5890 | 6 | Tab attacks marrowcuda; HP7 |
| 15 | 5891 | 7 | Tab destroys marrowcuda; HP8 |
| 16 | 5892 | 8 | Disengage south, retreat count1; HP10 |
| 17 | 5893 | 10 | Disengage south, count2, priest leaves sight; HP11 |
| 18 | 5894 | 11 | Blind attack northwest into wall, fallback wait; HP12 |
| 19 | 5895 | 12 | Blind attack north at nothing; HP14 |
| 20 | 5896 | 14 | Blind attack northeast into wall, fallback wait; HP15 |
| 21 | 5897 | 15 | Stale-unseen policy routes east toward upstairs, count3; HP16 |
| 22 | 5898 | 16 | Upstairs route southeast, count4; HP18 |
| 23 | 5899 | 18 | Upstairs route northeast, count5; HP19 |
| 24 | 5900 | 19 | Upstairs route northeast, count6, priest reappears; HP20 |
| 25 | 5901 | 20 | Tab rejected, no turn |
| 26 | 5901 | 20 | Rejected-Tab fallback pursues east; HP22 |
| 27 | 5902 | 22 | Tab rejected, no turn |
| 28 | 5902 | 22 | Fallback pursues east; HP23 |
| 29 | 5903 | 23 | Tab rejected, no turn |
| 30 | 5903 | 23 | Fallback pursues east; HP24 |
| 31 | 5904 | 24 | Tab rejected, no turn |
| 32 | 5904 | 24 | Fallback pursues southeast; HP25 |
| 33 | 5905 | 25 | Tab rejected, no turn |
| 34 | 5905 | 25 | Fallback pursues east; HP27 |
| 35 | 5906 | 27 | Tab rejected, no turn |
| 36 | 5906 | 27 | Fallback northeast into shallow water; Hand expires; HP29 |
| 37 | 5907 | 29 | No visible enemy: blind northwest attack fumbles in water; HP29 |
| 38 | 5908 | 29 | Priest visible again: Tab rejected, no turn |
| 39 | 5908 | 29 | Fallback northeast to floor exposes electric eel; HP30 |
| 40 | 5909 | 30 | Wizard memory expires; Tab pursues northeast; eel hits, HP21 |
| 41 | 5910 | 21 | Tab north into shallow water; eel/priest act, HP20 |
| 42 | 5911 | 20 | Tab northwest onto floor beside priest; eel hits, HP15 |
| 43 | 5912 | 15 | Tab slashes priest; eel hits, HP4 |
| 44 | 5913 | 4 | Melee nearly kills priest; priest smites13, death |

## Findings

1. Escape was not merely hypothetical. Decisions16-17 broke visual contact on
   dry ground, and the character recovered from8 to20HP by decision24. Staying
   safe forever is not proven, but immediate contact was demonstrably broken.
2. Real unseen-attacker evidence predates the steam. Messages include unseen
   melee and a magic dart. Thus the wizard concern was not invented solely
   because steam hid a visible enemy.
3. At5881, steam coincides with "Reactivating autopickup" and "You feel a bit
   more experienced." The morgue lists two orc wizards killed by others. This
   strongly suggests the unseen wizard died to collateral damage then; the
   bot never gets a named "You kill the orc wizard!" message. Exact identity
   at that moment is inference, not privileged monster-state observation.
4. hidden_missing remains true through5908. This suppresses berserk even at
   HP51-55 with the dragon adjacent, and sends the safely withdrawn character
   through blind probes and an upstairs path instead of ordinary recovery.
   Its stale memory lasts longer than20 turns after the last real evidence:
   the still-fresh disturbance flag refreshes hidden_caster.seen during the
   eight-turn disturbance window, then another20-turn memory window follows.
5. The upstairs path has no visibility-risk objective. It re-exposes the
   priest at5901 and consumes the sixth shared retreat step. No reset occurs
   when contact breaks. That budget then prevents further ordinary retreat.
6. Despite phase=disengage at every remaining action, combat falls through to
   Tab and the rejected-Tab fallback. The latter pursues through water. This
   is a control-flow violation of the encounter's intended action, not proof
   that all escape routes were exhausted. Native Tab eventually pursues too.
7. The unsafe-square handler cannot compare bad alternatives: when every
   neighboring floor tile is steam-covered at5881, it waits in steam. This
   is independently fragile, but the trace shows HP rose50->51 during that
   particular wait; it was not itself the decisive damage event.
8. The priest is grey(threat1) throughout; the eel is yellow(threat2). The
   original low-health collapse and subsequent re-engagement explain why
   a normally weak priest can finish the character. No cap note or wand use:
   the only wand is acid, which current selection does not support.

Priority for a later fix: preserve disengagement/recovery as an actual action
constraint across fallback paths, and distinguish stale unseen-caster memory
from fresh evidence. Add resource options afterward; fog alone could worsen
the same visibility-memory problem. No tactical repair was made in this replay.

## Reproduction details

Launch steam-debug-v1.json via batch.py using a fresh diagnostic version/name
if replaying again. The frozen RC contains the single-decision gate, snapshots
and command/action wrappers. At the breakpoint, these console-only logging
wrappers were additionally installed (they do not select gameplay actions):

```lua
local old=crawl.mpr
crawl.mpr=function(s,...)
  if s:find("^TRACE ") then crawl.take_note(s) end
  return old(s,...)
end
local msg=c_message
c_message=function(s,c)
  msg(s,c)
  if not s:find("TRACE ",1,true) then crawl.take_note("EVENT "..s) end
end
```

steam_step.py issued one autocrawl_steam_step() through the console, closed
the console to let ready run once, then printed autocrawl_steam_report() and
dumped the character. Every invocation was inspected before issuing the next.
The trace contains console-event noise, filtered only in the helper's output.
The terminal morgue retains the full notes. The character is now dead.
