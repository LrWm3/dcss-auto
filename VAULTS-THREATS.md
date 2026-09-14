# Vaults threat checklist — local 0.35, 2026-09-08

Research only; character unchanged at Time38865.9, Vaults1, HP173/173.
Online overview https://dcss.roguelikes.gg/wiki/The_Vaults is tagged 0.31;
individual thunderhulk/frostheart pages also old. Cross-checked local source
mon-pick-data.h (Vaults population), mon-spell.h, mon-data.h,
dat/descript/monsters.txt and spells.txt. Use in-game xv for actual encounters,
especially uniques, spell sets and wand success chances. No hidden map inspected.

## Immediate priorities

- Vault sentinel: mark reveals location to the whole floor. Hand BEFORE hex
  attempts, keep Midwinter Will+. If marked, leave to cleared floor promptly;
  do not rest on partly explored Vaults. Killing sentinel does not itself
  constitute a safe response to the already-active mark. No cancellation held.
- Vault warden: seals doors AND stairs. Exit proximity is not guaranteed safety.
  Kill/disable or break LOS early, prepare alternative retreat and early BiA.
  Do not wait until critically injured to start teleport. Most branch walls
  are undiggable; examine terrain before treating digging as an escape route.
- Ironbound convoker: delayed recall of existing intelligent allies, plus
  might. Kill/disable promptly when recall begins, or disengage; moving out
  of sight is not proof the recall was cancelled. Do not berserk into unknown
  rooms chasing it.
- Thunderhulk: lightning needs LOS, not a clear projectile lane. Cannot use
  it within distance2 (verified mon-cast.cc), but can blink away. NO rElec on
  character: break LOS, inspect charming/mindburst chances, summon help early;
  close only over safe ground. Resistance potion if committed to dangerous
  electricity fight. Hand is NOT elemental resistance.
- Frostheart: wall-adjacent cold attack; rC++ reduces damage but DOES NOT
  prevent movement-slowing freeze. Doorway/wall hugging is not universally
  safe. Prefer break LOS/disable; shift away from walls only if that doesn't
  expose us to the rest of a pack.
- Preserver: shares allies' injuries and heals itself. Two protectors can
  prolong a fight considerably. Isolate, prioritize exposed supporter, don't
  chase through guards. Our single-door fight worked.

## Other early-floor threats verified in local population / spell data

- Formless jellyfish: blink-close, constriction, damage37 sting and brief
  paralysis. Will does NOT counter this attack; rPois reduces paralysis
  frequency but isn't immunity (melee-attack.cc AF_MINIPARA). Ranged damage,
  helpers, isolation; never treat it as an ordinary slime or rage into a pack.
- Yaktaur/captain and centaur squads: break lines of fire around corners;
  shield not immunity. Dire elephants can threaten position; big merged slimes
  and buffed orc warlords demand isolation, not trading against a whole group.
- Arcanist: cold bolt, searing ray, Vitrify, haste. Vitrify increases damage
  from ALL sources. Great orb has Vitrify/confuse/poly/mindburst in this build;
  do not apply old paralysis spell lists blindly. Use Hand proactively.
- Sphinx marauder: confuse/Vex (forces attacks, losing movement control).
  Guardian sphinx begins normal generation V2: confuse/slow/paralyse/smite.
  Hand for Will checks, not protection against smiting. Examine each variant.
- Entropy weaver: corrosion; carry rCorr swap, prioritize or retreat rather
  than stay and trade with reduced defence. Boggart: summon snowball, prioritize.
- Ironbound mechanist: Forge Phalanx Beetle and All-Purpose Tempering; support
  caster for constructs. Peacekeeper has barbs plus battlecry; moving while
  barbed hurts. War gargoyle/crystal guardian bands are heavy threats:
  guardian Crystallising Shot can make us brittle. Examine, isolate; don't
  assume a wand/element works against highly resistant constructs.
- Polterguardian: missile-deflecting support aura and Force Lance; don't
  count on straight ranged shots or unchanged position. Crawling flesh cage:
  reaching/cleaving tentacle attack and broad elemental resistances.
- Uniques/out-of-depth enemies: examine individually, exclude if necessary.
  Especially electricity specialists without rElec; no blanket 'we can melee'.

## Run-specific plan

Clear rooms methodically, preserve retreat corridors, scout other permanent
stairs on each new floor. No V5 peek: its landing is a separate major challenge.
Gear stays slaying + Midwinter, faith; no immediate skilling change (F21->22).
Only rod1/4 ready, vane/box inert. Charm19/mindburst5/iceblast6 are intermediate
tools, inspect success. BiA can fail: use before crisis and adapt promptly.
Avoid berserk against unresolved control/support packs; it locks out items.
Prefer safe retreat/early teleport over forcing a seal/mark/freeze combination.

Online references:
- https://dcss.roguelikes.gg/wiki/The_Vaults
- https://dcss.roguelikes.gg/wiki/Ironbound_thunderhulk
- https://dcss.roguelikes.gg/wiki/Ironbound_frostheart
- https://dcss.roguelikes.gg/wiki/Ironbound_convoker
