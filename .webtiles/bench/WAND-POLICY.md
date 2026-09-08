# Wand experiment: HP/threat gate

Eligibility is `floor(10 * current_hp / max_hp) < threat_score` (HP score clamped
to 0..10). Visible hostile red/threat3 contributes6; yellow/threat2 contributes1;
other threats contribute0. The gate is recalculated after every action; it does
not use the peak roster as a danger score. A charm removes that ally's contribution.

Eligibility does not force a cast: identification, charge count, targeting safety,
success chance, and the existing charm/mindburst/warping selection rules still apply.
At full HP, Lodul plus three yellow ogres scores9 against HP10: no wand yet.
At HP<90%, that same group can open the gate. Equality never opens it.

Four spent wand actions maximum across an encounter. Rejected attempts do not
count, but cannot retry on the same turn. The budget survives LOS changes,
stairs, and save/load. It resets after no visible/unseen encounter activity
remains in memory, HP is full, and berserk/recovery status has ended.

The fourth cast produces a permanent `WAND CAP 4/4` character note, recording
the encounter start turn/floor and enemies seen, grouped by name/threat with
peak simultaneous counts. If more enemy kinds/counts join the capped encounter,
an updated note is added; unchanged rosters do not spam notes. This is not an
exact count of distinct monster identities, and changes in threat may appear
under multiple labels. No emergency override of the cap is currently permitted.
