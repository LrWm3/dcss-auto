# Beginner agent playbook: Minotaur Berserker of Trog

Goal: learn reliable terminal control, reach Lair alive, then pursue a three-rune
win. Survival takes priority over speed, loot, and clearing every enemy.

Before controlling a game, read `DCSS-MECHANICS.md`, including its mandatory
manual-skilling procedure and identification rules. Do not begin gameplay until
you can apply those rules to the actual character and screen.

Selected reading: [Malcolm Rose's Minotaur Berserker beginner guide](https://dungeoncrawlstonesoup.com/guides/mibe).
It is explicitly for 0.24. Use its broad character concept and positioning
lessons, not its old item names, branch depths, or numeric shield thresholds.
The operating rules and staged targets below are our conservative agent plan,
not a reproduction of that guide. Local 0.35-a0 descriptions take precedence.

## 1. Establish control before playing

- Read WEBTILES.md. Identify the exact terminal/session you own.
- Do not send input to another agent's character. Do not restart a live run
  merely because this playbook recommends a different background.
- On the next fresh run use `./play-webtiles.sh LunaMiBe` in a PTY, and select
  Minotaur, Berserker, and an axe by reading the actual menus.
- The existing AgentWatch demonstration is a Fighter, not a Berserker. Its
  abilities are different; never assume it has Trog powers.
- First demonstrate that you can inspect inventory, inspect a monster, open
  skills, leave a menu, and read the resulting screen without accidental moves.
- Use `?` whenever uncertain about a command. Inventory letters and ability
  letters can change: read the current menu rather than remembering a letter.

Useful default commands: `i` inventory; `m` skills; `a` abilities; `q` potion;
`r` scroll; `V` evoke; `x` then select a monster and `v` to inspect;
`.` wait one turn; `5` rest; `o` autoexplore; `<` ascend; `>` descend.
Confirm these in game if bindings differ. Rest can be interrupted; verify HP
and statuses afterward rather than assuming recovery completed.

## 2. Mandatory observation/action loop

Before each gameplay action, record briefly:

`HP | statuses | visible threats | position | safe exit | next action + reason`

1. Read the entire current terminal screen and recent messages.
2. Determine whether this is gameplay, a menu, targeting, or a confirmation.
3. Inspect unfamiliar threats. Check speed, ranged attacks, disabling effects,
   and damage; do not identify monsters solely by their terminal glyph.
4. Choose one action. Send it once, then capture a fresh screen.
5. Confirm the expected change before doing anything else.

Never queue `oooo`, many Tabs, or movement strings through unexplored space.
A single autoexplore command is allowed when fully recovered and no threat is
visible; read its stopping result. If a command seems ignored, inspect the
prompt rather than repeating it. Menus and inspection are opportunities to
think; real-time deliberation does not advance this turn-based game.

## 3. Build targets

Choose Strength on stat increases. Use one-handed axes, a shield when available,
and substantial armour; evaluate displayed attack delay and defenses after
equipment changes. Fill compatible auxiliary slots. Prefer dependable equipment
over an artefact whose drawbacks you have not understood.

Manual training is mandatory for this plan. Open `m`, use `/` if needed to
switch from automatic to manual, and verify the displayed training percentages.
Use the focus-selection mode to distinguish disabled `-`, normal `+`, and
focused `*`. Focus is double allocation weight, not bonus XP. Set targets with
`=` and the selected skill's current menu letter. Recheck after targets are met.

Suggested training checkpoints, not mandatory exact values:

- Start with Axes and Fighting, focusing Axes. First aim for Axes 8 and Fighting 5.
- Then develop Armour to about 5; add Shields when actually wearing a shield.
- Raise Axes toward the equipped weapon's displayed minimum-delay skill target.
  Do not train it indefinitely just because a larger number looks better.
- Continue Fighting and Armour; add modest Dodging and Evocations once you have
  useful devices. An early Evocations target of 3–5 is enough to begin evaluating
  their usefulness. Reassess at each branch, not every few turns.
- Do not train spells or Invocations for this Trog build. Check god descriptions
  before doing anything that could violate Trog's conduct; stay with Trog.

## 4. Combat rules

- Fight in explored terrain with an identified escape route. Draw enemies
  toward corridors and corners before they surround you.
- Against an ordinary approaching melee enemy, let it enter melee range rather
  than spending an unnecessary move stepping next to it.
- Against ranged enemies, break sight behind nearby cover where practical.
  Waiting in their firing lane is not the same tactic.
- An axe hitting several enemies does not make being surrounded desirable.
- Reposition early. Walking away from adjacent enemies can provoke opportunity
  attacks in this build; repeatedly walking away is not a dependable escape.
- Stairs also cost time. Adjacent enemies may follow. Use known cleared floors
  to isolate manageable opponents, not as an automatic rescue at critical HP.
- Skip dangerous uniques, sleeping threats, and optional vaults when needed.

Agent-specific alarms: below 80% HP, stop routine attacks and reassess; below
60%, normally commit to an escape or a strong survival resource. These are
conservative prompts, NOT safe thresholds: an enemy capable of lethal damage
in one or two actions requires an earlier response even at full HP.

## 5. Use resources deliberately

Before a hard fight, read the ability menu and available consumables.

- Berserk is for a short, committed melee fight with a safe recovery area.
  It restricts actions and leaves you slowed afterward. Never make a plan that
  requires reading a scroll or drinking a potion while berserk. If the fight
  calls for berserk, use it while healthy enough to benefit, not as a panic reflex.
- Trog's Hand supplies regeneration and extra willpower. Use it before relevant
  disabling magic or sustained damage; it is not an instant full heal.
- Brothers in Arms is support for a serious fight, available later. Summon
  help while there is still time for it to matter. Pre-summoning for an imminent
  hard fight is useful, but it is NOT a prerequisite: if an engagement becomes
  messy, reassess and summon then rather than continuing unsupported or
  reflexively berserking. Check the displayed failure chance and leave room for
  failure; helpers are an option, not a guaranteed rescue. Consider them before
  berserk restricts your actions and before HP becomes critical.
- Teleportation takes time. Read it early enough to survive the delay; its
  destination is uncertain. Blink is a different, more immediate positioning tool.
- Identify emergency resources in safety. Check potion/scroll descriptions and
  targeting prompts. Spend a known useful resource instead of gambling on an
  unidentified item when a dependable option exists.
- Avoid fighting hydras with an ordinary chopping axe. Skip them or use a
  suitable alternative, ranged resources, or allies after inspecting the matchup.

Optional per-character rc setting: `autofight_stop = 80`. This only blocks
autofight below a percentage; it does not protect manual movement/attacks.
Do not edit a shared rc or another player's settings without coordination.

## 6. Progression checkpoints

First milestone: reach D:4 alive while following the observation loop.
Second: reach Lair with known survival consumables and a coherent equipment set.
Do not treat a fixed turn count or speed target as success.

Working route for this local build, subject to threat checks:

1. Dungeon toward the Lair entrance (D:8–11).
2. Lair:1–5; postpone a dangerous ending or particular fight.
3. Dungeon to roughly D:12, then Orc:1–2 when ready, then Dungeon to D:15.
4. First three floors of the two Lair rune branches, choosing the order from
   current defenses; then their fourth floors for the first two runes.
5. Vaults:1–4 and Depths:1–4, deferring dangerous encounters.
6. Make a specific third-rune plan for Vaults:5 or Slime:5 from the actual
   character, resistances, consumables, and threats. Neither is a routine floor.
7. Zot:1–5, obtain the Orb, and return to the Dungeon:1 exit. During the Orb run,
   prioritize reaching the exit over clearing enemies.

Avoid optional timed portals, Elf, Crypt, and extended branches during initial
learning runs. Before each rune ending and Zot, pause for an equipment and
escape-resource review. The next branch is an option, not an obligation.

## 7. Learning and handoff

At each floor change, leave a short status: character, floor, HP, weapon,
skills, escape resources, deferred threats, and next objective. Keep the
terminal session name in the handoff so another controller cannot confuse games.

After a death, read the morgue and identify the earliest avoidable commitment,
not just the final killing blow. Record one concrete rule to change. Keep the
same species/background on subsequent attempts to make progress comparable.

Local references used to check the adaptation:
`crawl-0.35/crawl-ref/source/dat/descript/ability.txt` (Trog abilities),
`crawl-0.35/crawl-ref/source/mon-act.cc` (opportunity attacks),
`crawl-0.35/crawl-ref/source/branch-data.h` (branch lengths), and
`crawl-0.35/crawl-ref/docs/options_guide.txt` (autofight settings).
