# Lodul breakpoint inspection

Character CodexLodulDebug1, seed 13772526223844354029, session codex-bench2.
Paused on D10 at turn 8128, displayed time 8397.4. HP 91/91, XL10,
Evocations 4.8, no active status effects. No gameplay action taken after pause.
The game's live dump is retained separately as lodul-debug-v1-CodexLodulDebug1.txt.

Read-only Lua console query of visible monsters using `m:defeat_wl("Charm",true)`
and `m:defeat_wl("Mindburst",true)` returned:

| Monster | Relative coordinates | Charm success | Mindburst success |
| --- | --- | --- | --- |
| Lodul | -5,3 | 44% | 67% |
| Ogre | -5,2 | 62% | 81% |
| Ogre | -4,1 | 62% | 81% |
| Ogre | -3,1 | 62% | 81% |

Known wands: charming13, mindburst15 (3d13), warping10 (3d10), digging5.
Warping target preview showed 67% blink chance against an ogre. Moving the
cursor to the empty square (-4,2) did not produce a four-monster explosion:
the front monsters intercepted the beam and only the front two ogres were
highlighted. Preview cancelled; charges and displayed time unchanged.

Proposed opening: charm a front ogre while there is distance and full HP, then
re-evaluate. It changes pack pressure rather than merely adding damage. Mindburst
is a candidate for removing a wounded threat; prefer higher success unless a
lower-probability target is substantially more valuable. Warping needs explicit
blast/line-of-fire safety and becomes less attractive after charming an ally.
These are evaluated options, NOT a tested automatic wand policy or a won fight.

The original diagnostic mistakenly queried spell name "Charming" and reported
nil. Local engine spell-data names it "Charm"; corrected direct query produced
the values above without taking a turn. Canonical RC corrected and regression
tested. The live game remains on the original immutable snapshot, paused.
Resume deliberately with `autocrawl_debug_resume()` in the Lua console; the
original loaded combat policy still does not use these wands automatically.
