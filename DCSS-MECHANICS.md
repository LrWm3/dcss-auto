# Required mechanics review before playing

Checked against the local Crawl 0.35-a0 manual, item descriptions, skill menu,
item-use code, and monster spell lists. These are practical rules for the
Minotaur Berserker plan, not a claim that every encounter has a fixed solution.
Read the current in-game descriptions when an interaction is uncertain.

## Manual skilling

Use manual training from the start. Open `m`, switch with `/` if currently on
automatic, and verify the displayed mode. In the focus-selection mode, skills
cycle through disabled `-`, enabled `+`, and focused `*`. Use the menu's mode
switch (`|` or Tab) if it is only offering enable/disable. Read the labels.

Manual XP is divided between enabled skills, with a focused skill weighted twice
as heavily. Axes `*` plus Fighting `+` allocates approximately 67%/33%; it does
not create extra XP. Aptitudes affect how much progress that XP purchases, and
skill levels become progressively more expensive. Do not enable everything.

Use `=` to enter target-setting mode, select the skill by its current letter,
and enter the target. A target stops training when reached; it is not a promise
of attaining the level immediately. Inspect the allocation again after reaching
a target or changing equipment. Never assume old menu letters still apply.

For MiBe: Axes focused, Fighting enabled, everything else disabled initially;
use the playbook's first checkpoints, then make explicit changes for Armour,
Shields, and Evocations. Weapon inspection provides its minimum-delay target.
Minimum delay is a speed breakpoint, not the point at which all weapon-skill
benefits vanish. Attack delay also depends on equipment penalties and brands.
Heavy-brand weapons require special attention to their displayed delay.

Train Shields when wearing one; do not use obsolete fixed 'penalty removed'
thresholds from old guides. Fighting increases HP and physical combat ability;
Armour improves AC from armour; Dodging and Shields improve different defenses.
Do not train Unarmed Combat for a Minotaur's auxiliary headbutt. Trog powers do
not need Invocations. Do not train Spellcasting or spell schools under Trog.

`default_manual_training = true` can be put in the character's rc for future
starts, but check the current character's actual mode regardless. A found skill
manual is a separate consumable training bonus, unrelated to manual mode.

## Identifying scrolls and potions

Scroll labels and potion appearances do not reveal their type across runs.
Once a type is identified, other items of that type are recognized. Stack size
is a probability clue, never proof. Equipment, talismans, and wands identify
when stepped on in this build; do not spend scrolls trying to discover their
properties or wear an item blindly to identify it.

Prefer identify scrolls for unknown potions, especially while still missing
known healing and survival tools. Identifying a stack makes multiple doses
usable, but the best choice depends on which types remain unknown. Do this
early in the Dungeon, not only on arrival at Lair.

Read-identifying unknown scrolls is a managed risk:

1. Recover HP and clear the level as far as practical. Use explored terrain
   with no enemies or allies in sight, ideally on a cleared floor. Being next
   to stairs alone does not make an unexplored floor safe for random teleport.
2. Have useful enchantment targets and unknown potions in inventory so a
   discovered enchantment/identify scroll is not wasted unnecessarily.
3. Read one unknown type, inspect the result, and handle its prompt deliberately.
   Do not assume cancelling a newly discovered scroll refunds it.
4. If it teleports you, reassess the new position. If it creates poison clouds,
   stay on the initially unoccupied-by-cloud reader tile while safe rather
   than walking into poison. If it causes torment, recover the lost HP. If
   silence or vulnerability appears, wait safely for it to expire.
5. Noise may attract enemies; stop the experiment immediately if one appears.
   Expect some useful consumables to be consumed by this process.

Do not drink unidentified potions routinely. Lignification prevents movement
and teleportation; attraction pulls enemies toward you; ambrosia confuses;
moonshine impairs combat and casting; mutation can have lasting downsides.
Blind drinking is a last-resort gamble when known alternatives are worse, not
a substitute for identifying emergency supplies in advance.

## Stair dancing and luring

Use a known cleared upper floor as a place to fight a manageable follower.
First lure toward the upstairs while there is still separation. Let only the
intended enemy or small group approach, ascend while healthy enough to survive
the action, fight those that follow, and recover before going down again.
Adjacent eligible monsters can follow. Stair travel consumes time. Do not assume
it saves a low-HP character surrounded by enemies or under ranged fire.

Run lesson (CodexMiBe, Lair:2): stair dancing suits moderate threats or packs
that can be split into manageable followers. A hydra, water moccasin, and wraith
together were too much for that character's landing. Mark known crowded stairs
unsafe and choose another approach to scout and lure with more control. Do not
re-enter a known strong pack expecting to muscle through; the Nergalle landing
was an earlier warning of the same pattern. If alternate routes also have
problems, postponing the floor is valid. Bad luck in the available approaches
does not require forcing one of them.

A newly encountered downstairs situation offers a chance to act, but previously
visited stairs are not guaranteed harmless. If an entrance is crowded, consider
another staircase. Branch entrances often offer fewer alternatives. Nets,
constriction, disabling effects, and special monsters can spoil a retreat plan;
check the actual status and messages. Never use the D:1 exit before the Orb unless
deliberately abandoning the run.

Lure toward explored ground, preferably around a corner or into a narrow
approach. Withdraw on first sight rather than charging into an unexplored pack.
Let a melee enemy spend the final approach action when practical. Do not simply
wait in a ranged enemy's firing lane. Monsters can shout and combat makes noise,
so a one-enemy fight may attract reinforcements.

Breaking line of fire is not always breaking line of sight: a monster between
you and an orc priest does not stop its smiting. A wall/corner that breaks sight
does. Corridors are useful, but merging slime creatures are a counterexample to
'every enemy is safer in a corridor'. Read monster-specific mechanics.

Walking away from an adjacent pursuer can provoke opportunity attacks. Repeated
same-speed kiting or pillar circling is not a dependable recovery technique.
Fast enemies can catch you even without that mechanic. Choose haste, blink,
early teleport, a control effect, allies, or a favorable fight as appropriate.

## Items and action restrictions

- Curing heals a little and cures poison/confusion. Heal wounds supplies larger
  immediate healing but does not substitute for curing poison. Assess both
  current HP and pending poison damage.
- Haste helps movement and other actions. Might helps melee damage. Resistance
  covers several elements but is not extra Will. Enlightenment supplies flight
  and Will. Flight is not protection from ranged enemies.
- Berserk restricts you to movement and melee, then leaves slow/exhaustion.
  Apply needed buffs before raging; do not plan to quaff or read during it.
- Teleport is delayed and random. Reading teleport again cancels a pending one.
  Blink chooses a nearby position, subject to restrictions. Choose a destination
  that actually breaks the danger, not merely another square in the same pack.
- Fog takes a short time to fill out. Fear has resistance/immunity considerations.
  Summoning/butterflies can create space but do not guarantee protection from
  smite-targeted or penetrating attacks. Poison clouds can constrain your exit.
- Immolation and torment are dangerous offensive tools, not generic panic buttons.
  Silence also blocks your scrolls and divine invocations; some monster abilities
  still work through it. Cancellation can remove useful effects as well as bad.
- Wands and throwing provide ranged damage/control. Check target resistance,
  displayed success chance, range, trajectory, charges, and friendly fire.
  Trog permits useful evocations; being a melee character is no reason to ignore
  them. Nets and curare are tools to inspect for suitable targets.
- Compare weapon base damage, brand, enchantment, skill, and delay, not just its
  name or plus number. Armour and amulet changes take time; make them safely.
  Read artefact drawbacks and maintain suitable resistances for the next threats.

## Stats, defenses, and spells

For this axe build, Strength is the default level-up choice: it improves relevant
physical damage and reduces equipment penalties. Dexterity helps accuracy,
evasion, shields, and blade/ranged damage. Intelligence helps spell power and
success. Attributes are not interchangeable with skills or character level.

AC reduces applicable damage, EV avoids dodgable attacks, and SH blocks eligible
attacks. None replaces HP, positioning, or resistances. Will helps against many
hexes such as ordinary Confuse/Paralyse/Banishment, not every disabling effect.
Inspect the enemy's actual ability and displayed chance; more Will is not blanket
immunity. Elemental resistance helps the corresponding damage, not all damage.

Trog forbids spellcasting: this character uses god powers, evocations, and items.
For other characters, having a spell in the library is not having it memorized
or reliably castable. Check spell schools, failure rate, power, range, MP cost,
target resistance, and noise. Armour/shield changes can spoil casting success.
Do not train an entire magic curriculum for one uncastable high-level spell or
plan to finish a fight with MP you do not have.

Understand hostile magic even when not casting: projectiles need suitable
trajectories; smiting needs sight but no clear firing line; some disabling
effects check Will and others do not; poison continues damaging after the caster
dies; paralysis prevents taking rescue actions. Buff or disengage before control
is lost. Killing a summoner can help against its summons, but inspect the actual
summon rather than assuming every summoned effect disappears identically.

## Common threats and first responses

| Threat | What makes it dangerous | Initial response |
| --- | --- | --- |
| Adders, water moccasins | Speed and poison | Isolate; avoid outrunning by assumption; account for poison and keep curing ready. |
| Gnoll packs | Multiple attackers, polearm reach, possible nets | Pull a few; inspect weapons; do not fight behind a net-blocked escape. |
| Ogres, orc warriors | Large individual hits or strong equipment | Do not judge safety from HP percentage alone; use resources or defer. |
| Orc priests | Smiting through other monsters | Break sight promptly; avoid standing in sight of multiple priests. |
| Orc wizards / Sigmund | Confusion, invisibility, ranged magic; Sigmund also reaches with a scythe | Inspect; use Will support/cover; defer Sigmund unless prepared. |
| Grinder | Paralysis and pain | Avoid early; use Will support before exposure, never after paralysis starts. |
| Ijyb / wand carriers | Dangerous equipment can change the matchup | Inspect gear and messages; do not treat as an ordinary goblin. |
| Centaurs | Ranged damage and speed | Use nearby cover; do not casually cross an open room toward them. |
| Sleepcaps | Sleep sets up dangerous follow-up hits | Inspect and respect even when they look like trivial fungi. |
| Jellies | Acid/corrosion punishes melee | Prefer suitable ranged tools or defer; check defenses after corrosion. |
| Hydras | Many attacks; chopping can grow heads | Flaming cauterizes, but does not guarantee a safe fight; use appropriate alternatives or skip. |
| Orc sorcerers / banishers | Disabling spells, demons, or banishment | Inspect spell list and Will chances; break sight or commit resources early. |

Before fighting anything unfamiliar, inspect it. A named monster's current gear,
allies, and position can matter as much as its species. Learning means identifying
the earliest bad commitment after a loss, not merely remembering its killer.

## Evidence

- `crawl-0.35/crawl-ref/source/skill-menu.cc`: mode controls, allocation, focus, targets.
- `crawl-0.35/crawl-ref/source/items.cc`: identification on stepping onto equipment/wands.
- `crawl-0.35/crawl-ref/source/item-use.cc`: unknown-scroll effects and identification.
- `crawl-0.35/crawl-ref/source/dat/descript/items.txt`: consumable descriptions.
- `crawl-0.35/crawl-ref/source/mon-act.cc`: pursuit/opportunity attacks.
- `crawl-0.35/crawl-ref/source/mon-spell.h`: priest, wizard/Sigmund, and Grinder spell sets.
- `crawl-0.35/crawl-ref/source/dat/descript/monsters.txt`: hydras and other monster mechanics.
- `crawl-0.35/crawl-ref/docs/crawl_manual.rst`: stats, stairs, items, and spellcasting.
- [Upstream manual](https://github.com/crawl/crawl/blob/master/crawl-ref/docs/crawl_manual.rst).
