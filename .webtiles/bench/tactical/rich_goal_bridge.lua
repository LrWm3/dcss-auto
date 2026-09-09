-- Observation-only extension. Uses managed player-visible APIs, not dungeon Lua.
local previous_goal_observation=goal_observation
local skills={"Fighting","Short Blades","Long Blades","Axes","Maces & Flails",
  "Polearms","Staves","Ranged Weapons","Throwing","Armour","Dodging",
  "Stealth","Shields","Unarmed Combat","Spellcasting","Conjurations",
  "Hexes","Summonings","Necromancy","Translocations","Forgecraft",
  "Fire Magic","Ice Magic","Air Magic","Earth Magic","Alchemy",
  "Invocations","Evocations","Shapeshifting"}

function goal_observation(state)
  previous_goal_observation(state)
  state.rich_version=2
  local p={skills={}}
  for _,key in ipairs({"xl","ac","ev","sh","strength","intelligence",
      "dexterity","res_poison","res_fire","res_cold","res_draining",
      "res_shock","res_corr","willpower","see_invisible","flying",
      "species","class"}) do
    assert(type(you[key])=="function","missing player observation API: "..key)
    p[key]=you[key]()
  end
  p.mp,p.max_mp=you.mp()
  for _,skill in ipairs(skills) do p.skills[skill]=you.skill(skill) end
  state.player=p
  state.gear={}
  for i,it in ipairs(items.inventory()) do
    local g={name=item_name(it),class=item_class(it)}
    -- Item attributes are properties; damage_rating is a bound closure.
    for _,key in ipairs({"equipped","equip_type","quantity","plus",
        "damage","accuracy","delay","ac","encumbrance","weap_skill",
        "is_ranged","is_shield","is_melded","reach_range","artprops"}) do
      g[key]=it[key]
    end
    g.subtype=it.subtype(false);g.ego=it.ego()
    g.damage_rating=it.damage_rating()
    state.gear[i]=g
  end
  state.enemy_details={}
  for i,e in ipairs(scan_hostiles().monsters) do
    local m=e.monster
    local d={x=e.x,y=e.y,threat=e.threat,reachable=e.reachable}
    for _,key in ipairs({"name","type","base_type","damage_level","damage_desc",
        "max_hp","ac","ev","wl","res_poison","res_fire","res_cold",
        "res_draining","res_shock","res_corr","speed_description","spells",
        "status","range","reach_range","is_unique","is_stationary",
        "is_constricting_you"}) do d[key]=m[key](m) end
    state.enemy_details[i]=d
  end
end
