# Observed wand actions

Same live character as the Lodul breakpoint, without resetting combat or rerolling.
Policy selected the nearest front ogre at (-3,1), score109.2, for charming;
warping on that ogre was also a candidate, score76, covering two hostiles.

Message history confirmed this sequence of successful action executions:

1. Charming -> ogre (-3,1), 62%, reduce pack pressure. Ogre charmed.
2. Mindburst -> ogre (-3,0), 81%, remove wounded attacker. Mind blasted.
3. Mindburst -> ogre (-2,0), 81%, remove wounded attacker. Mind blasted.
4. Charming -> ogre (-4,1), 62%, reduce pack pressure. Ogre charmed.

Opening still incurred a 20HP lightning hit from Lodul; the allied ogre attacked
another ogre on that turn. The later dump records an allied ogre being killed,
Lodul killed at turn8143, and additional ogres killed. At turn8149 character was
77/97HP, XL11, with another visible ogre. Ran 30 more controller turns: turn8179,
91/97HP, no visible enemies, paused deliberately. Charming13->11,
mindburst15->13, warping10 unchanged. No claim that all D10 is cleared.

Execution investigation: item.slot exposes a category letter index in this
checkout, whereas items.fire indexes the backing inventory. Initial invocation
spent neither charge nor turn. A second probe also did nothing because
crawl.read_options silently skips already-included filenames: the same-path
reload did not install the fix. Loading unique snapshot lodul-wands-780ebd2.rc
installed the corrected wand-menu execution. Failed-attempt bookkeeping was
cleared before the working test; no character HP/position/RNG restoration.
Normal evoke menu V + category letter, r to centre targeting on player, explicit
relative cursor moves, f and Escape guards now execute the selected wand.

The policy has no Lodul-specific combat rule. It avoids berserk/confused use,
unknown/empty wands, intervening creatures/ambiguous terrain, nearby allies in
warping blasts, repeated same-turn attempts, and excessive recent wand use.
It considers charm on dangerous packs at >=60% success, mindburst against
visibly heavily wounded or worse threats at >=65%, and safe two-hostile blasts.
It uses visible injury buckets, not exact hidden HP. Candidate scores are simple
heuristics, not a calibrated melee-versus-wand damage model.

Character left paused in codex-bench2 with the corrected RC loaded. The previous
lodul-debug-v1 benchmark row remains the original pause; this episode is recorded
separately in interventions/lodul-wands-v1.json, not promoted as an autonomous run.
