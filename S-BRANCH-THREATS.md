# Spider / Swamp preparation (local 0.35, 2026-09-07)

Background references (OLDER version tags, not definitive current mechanics):
- https://dcss.roguelikes.gg/wiki/Swamp (0.30)
- https://dcss.roguelikes.gg/wiki/Spider%27s_Nest (0.31)

Cross-checked local crawl-0.35/crawl-ref/source/mon-data.h, mon-spell.h,
and dat/descript/monsters.txt. Examine actual encounters for damage, abilities,
and hex chances. Do not assume older wiki mechanics or threat rankings.

## Swamp

- Terrain: open watery floor, sparse tree cover. Flight ring available; replace
  slaying rather than Midwinter (Will/rC/EV). Fight on dry land otherwise.
- Hydra: swap to +4 freezing morningstar before contact; elec axe grows heads.
- Alligator: fast, bite DRAGS, especially dangerous by water/other monsters.
- Swamp worm: Harpoon Shot pulls us. Don't allow pull into unexplored water/pack.
- Goliath frog: reaching acidic tongue. Swap spare rCorr ring early if fighting;
  corrosion plus other melee enemies is reason to disengage, not keep trading.
- Bloated husk: fast undead explodes on contact OR destruction. Kill from range,
  not adjacent. Fear inappropriate for undead. Don't assume rPois stops blast.
- Bunyip: three base40 claws, fast movement but long attack recovery; warning
  cry attracts threats. Isolate, don't judge by its slow attack frequency alone.
- Eleionoma: tree movement, Splinterspray and Woodweal; don't give free tree
  approach/healing. Examine actual ranges and damage before engagement.
- Fenstrider witch: Paralyse / Agonising Touch / Hurl Sludge. TrogHand EARLY
  for Will; check paralysis chance. Prefer retreat from a witch plus a pack.
- Bog body: Bolt of Cold + Slow. Our rC++ helps, but slow threatens retreat.
- Spriggan druid: Stone Arrow, Druid's Call, Awaken Forest, healing. Tree cover
  can become danger; break LOS and isolate. Don't wait through summons.
- Will-o-the-wisp: local spell is MARSHLIGHT + blink, not assume old foxfire.
  rF++ useful; examine exact spell when encountered.
- Ghost crab: Spectral Cloud. Leave clouds, avoid trading with summoned spirits.
- Thorn hunter: Thorn Volley and Wall of Brambles; obstruction + ranged damage.
- Swamp drakes/dragons: rPois helps gas; still respect physical damage.
- Uniques / rune endings: examine and reassess, no automatic commitment.

## Spider

- Common spiders fast, evasive, swarm. rPois helps but is NOT general immunity.
- Tarantella: confusing touch (not ordinary poison); curing ready.
- Jumping spiders: webs/rapid approach. Don't wait to be surrounded or webbed.
- Jorogumo: Bolt of Draining + Ensnare; melee AF_POISON_PARALYSE. Different
  threat from witch's Will-check paralysis; do not conflate defenses.
- Orb spider: Orb of Destruction. Break firing line/use terrain, don't charge
  through an orb or let it shoot while fighting something else.
- Entropy weaver: Entropic Weave corrosion, many melee hits; isolate/rCorr.
- Torpor snail: presence slows. Break LOS/kill it before trying to run a pack.
- Moth of wrath: berserks allies. High priority; don't melee berserk swarm.
- Pharaoh ant: death binds allied souls -> simulacra on later deaths. Separate
  it from pack if possible; rC++ helps resulting simulacra, not a license to swarm.
- Culicivora heals others + vampiric bite; broodmother summons spiders.
- Demonic crawler rapidly regenerates: sustained damage, not weak ranged pokes.
- Steelbarb worm embeds barbs; repeated movement costly. Fast despite armour.
- Radroach: Irradiate (natural). Dangerous adjacent burst/contamination.
- Spark wasp: fast electric attacks; no permanent rElec currently, resistance
  potion if needed, preferably don't engage together with other threats.
- Sun moth: Pyre Arrow and halo; invisibility not dependable in its halo.
- Ghost moth: invisible, hard melee, resource drain; no SInv currently. Don't
  assume it is harmless to a berserker just because we don't cast spells.

## Current constraints

HP147, AC20 EV13 SH14, rPois/rF++/rC++, Midwinter Will+, flight/rCorr swaps.
No rElec/rN/SInv. BiA currently unavailable (Trog***); restore piety through
safe kills, never assume helper availability. Rod2/4, box inert, fear1/haste1,
teleport7, fog1, healwounds2. Preserve escape options by leaving early.
Scout Swamp1 entrance only initially; no commitment to rune floor.

D14 CENTRAL/EAST and SW downstairs now each have radius-zero exclusions,
verified by cycling map E between the two staircase locations. They lead to
the dangerous D15 packs described in CODEX-MIBE-RUN.md. Do NOT remove casually.
