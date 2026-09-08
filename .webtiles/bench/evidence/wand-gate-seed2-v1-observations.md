# Gated replay observations

CodexWandGate1, seed13772526223844354029, started fresh using RC6638c14e…
(full hash in runs.jsonl), no gameplay intervention. Stopped at turn24759 on
Shoals:2, XL15, HP137/137, mesmerised by a merfolk avatar and siren. The existing
movement-rejection guard prevents further automation after an attempted move
away from a mesmeriser. Preserved alive in codex-bench1. This is a pause, not death.

Read-only Lua console check AFTER the pause (no turn advanced):

```
crawl.mpr("D15="..tostring(ROUTE_STATE.done["D:15"]).." route_stage="..ROUTE_STATE.index.." turn="..you.turns())
D15=clear route_stage=6 turn=24759
```

Thus D15 was explicitly marked clear by the controller, not just reached by a
shaft. We have not measured the entire cleared route prefix, so the benchmark's
cleared_prefix remains null. Dump creation and this read-only query were the
only game inputs after starting the autonomous trial.

Wand consumption: charming3, mindburst5, warping2 =10 casts, versus38 casts in
the prior D11 death. Remaining: charming16, mindburst17, warping20 (additional
pickups mean these counts are not simply original inventory minus usage).
Lodul killed turn8056; D11 ogre mage killed turn10202.

One encounter reached the four-cast cap: start22304, D15, cap note22341.
Enemy roster included basilisk, centaur warrior, culicivora, cyclops, red/white
ugly things, centaurs, yaktaurs, and slime creatures. At22421 the same cap note
was updated with a tengu conjurer joining the roster. Full peak counts and
threat labels are in the permanent notes of the accompanying dump. These are
two notes for ONE capped encounter, not two cap hits. HP dipped to6/131 during
that encounter, and the character survived without overriding the cap.

Single-seed screening result only: strongly lower consumption and farther
progression, but no causal proof or five-seed minimum improvement. RC retained
unchanged; mesmerisation recovery is a separate outstanding issue.
