-- General semantic-action bridge.
--
-- This file is appended inside the existing RC Lua block.  The historical
-- MiBe controller is deliberately left loaded, but paused before its ready()
-- hook is called.  The bridge owns one decision boundary at a time and never
-- asks the learner to emit raw menu keystrokes.

AUTOCrawl_DEBUG_STATE.paused = true
BOT.paused = true

local ga_parent_ready = ready
GENERAL_AGENT = GENERAL_AGENT or {active=true, seq=0, published=-1, actions={}}
local GA = GENERAL_AGENT

-- The rejected-action mask is adapter state, but it affects action indexing.
-- Include it in Crawl's embedded Lua save hook so clones enumerate identically.
table.insert(chk_lua_save, function()
  local entries = {}
  for key, value in pairs(GA.rejected_actions or {}) do
    if value then entries[#entries+1] = "[" .. string.format("%q", key) .. "]=true" end
  end
  table.sort(entries)
  return "GENERAL_AGENT = GENERAL_AGENT or {active=true,seq=0,published=-1,actions={}}; "
    .. "GENERAL_AGENT.rejected_turn=" .. tostring(GA.rejected_turn or "nil") .. "; "
    .. "GENERAL_AGENT.rejected_actions={" .. table.concat(entries, ",") .. "}\n"
end)

local GA_MOVES = {
  {dx=-1,dy=0,key="h",cmd="CMD_MOVE_LEFT"},
  {dx=0,dy=1,key="j",cmd="CMD_MOVE_DOWN"},
  {dx=0,dy=-1,key="k",cmd="CMD_MOVE_UP"},
  {dx=1,dy=0,key="l",cmd="CMD_MOVE_RIGHT"},
  {dx=-1,dy=-1,key="y",cmd="CMD_MOVE_UP_LEFT"},
  {dx=1,dy=-1,key="u",cmd="CMD_MOVE_UP_RIGHT"},
  {dx=-1,dy=1,key="b",cmd="CMD_MOVE_DOWN_LEFT"},
  {dx=1,dy=1,key="n",cmd="CMD_MOVE_DOWN_RIGHT"},
}

local function ga_call(obj, name, ...)
  if not obj then return nil end
  local f = obj[name]
  if type(f) ~= "function" then return nil end
  local ok, value = pcall(f, obj, ...)
  if ok then return value end
  return nil
end

local function ga_bool(value)
  return value and true or false
end

local function ga_you(name, ...)
  local f = you[name]
  if type(f) ~= "function" then return nil end
  local ok, first, second, third = pcall(f, ...)
  if ok then return first, second, third end
  return nil
end

-- The original tactical bridge used an object-only encoder.  This version
-- emits real JSON arrays when a table has contiguous integer keys, which keeps
-- the Python action interface straightforward while retaining object maps.
local function ga_json(value)
  if type(value) == "string" then
    return '"' .. value:gsub('[%z\1-\31\\"]', function(c)
      return string.format('\\u%04x', string.byte(c))
    end) .. '"'
  elseif type(value) == "number" then
    if value ~= value or value == math.huge or value == -math.huge then return "null" end
    return tostring(value)
  elseif type(value) == "boolean" then
    return tostring(value)
  elseif type(value) == "table" then
    local max, count, array = 0, 0, true
    for key, _ in pairs(value) do
      if type(key) ~= "number" or key < 1 or key ~= math.floor(key) then
        array = false
      else
        if key > max then max = key end
        count = count + 1
      end
    end
    local out = {}
    if array and max == count then
      for i=1,max do out[#out+1] = ga_json(value[i]) end
      return "[" .. table.concat(out, ",") .. "]"
    end
    for key, item in pairs(value) do
      out[#out+1] = ga_json(tostring(key)) .. ":" .. ga_json(item)
    end
    table.sort(out)
    return "{" .. table.concat(out, ",") .. "}"
  end
  return "null"
end

local function ga_item_class(item)
  local value = ga_call(item, "class", true)
  return string.lower(tostring(value or ""))
end

local function ga_item_name(item)
  local value = ga_call(item, "name")
  return string.lower(tostring(value or ""))
end

local function ga_level()
  return tostring(ga_you("branch") or "unknown") .. ":"
      .. tostring(ga_you("depth") or 0)
end

local function ga_map_key(x, y)
  return tostring(x) .. ":" .. tostring(y)
end

local function ga_map()
  local result = {}
  for _, cell in pairs(view.get_map()) do
    if cell and cell.x ~= nil and cell.y ~= nil then
      result[ga_map_key(cell.x, cell.y)] = cell
    end
  end
  return result
end

local function ga_monster_detail(monster, x, y, threat, reachable)
  local detail = {x=x, y=y, threat=threat, reachable=reachable}
  for _, key in ipairs({"name", "type", "base_type", "damage_level", "damage_desc",
      "max_hp", "ac", "ev", "wl", "res_poison", "res_fire", "res_cold",
      "res_draining", "res_shock", "res_corr", "speed_description", "spells",
      "status", "range", "reach_range", "is_unique", "is_stationary",
      "is_constricting_you"}) do
    local value = ga_call(monster, key)
    if value ~= nil then detail[key] = value end
  end
  return detail
end

local function ga_enemy_scan(cells)
  local monsters, blocked = {}, {}
  for _, cell in pairs(cells) do
    if cell.visible and cell.monster then
      local monster = cell.monster
      local attitude = ga_call(monster, "attitude")
      local firewood = ga_call(monster, "is_firewood")
      local name = tostring(ga_call(monster, "name") or "")
      if attitude == 0 and not firewood and name ~= "butterfly"
          and name ~= "orb of destruction" then
        local reachable = false
        local ok, value = pcall(view.can_reach, cell.x, cell.y)
        if ok then reachable = value and true or false end
        local threat = ga_call(monster, "threat") or 0
        monsters[#monsters+1] = ga_monster_detail(monster, cell.x, cell.y,
          threat, reachable)
        blocked[ga_map_key(cell.x, cell.y)] = true
      end
    end
  end
  table.sort(monsters, function(a, b)
    if a.y ~= b.y then return a.y < b.y end
    return a.x < b.x
  end)
  return monsters, blocked
end

local function ga_cell_passable(cell)
  return cell and (cell.traversable or (cell.x == 0 and cell.y == 0))
      and cell.feature ~= "enter_shop" and not cell.excluded
end

local function ga_target(monsters)
  local best
  for _, monster in ipairs(monsters) do
    local distance = math.max(math.abs(monster.x), math.abs(monster.y))
    if not best or distance < best.distance then
      best = {x=monster.x, y=monster.y, distance=distance}
    end
  end
  return best
end

local function ga_add(actions, action)
  local key = table.concat({action.kind or "", action.slot or "", action.name or "",
    action.x or "", action.y or "", action.dx or "", action.dy or "", action.item_name or ""}, "|")
  if GA.rejected_turn == ga_you("turns") and GA.rejected_actions and GA.rejected_actions[key] then
    return
  end
  if #actions < 88 then
    action.id = #actions
    actions[#actions+1] = action
  end
end

local function ga_actions(cells, monsters, blocked)
  local actions = {}
  local target = ga_target(monsters)
  for _, move in ipairs(GA_MOVES) do
    local cell = cells[ga_map_key(move.dx, move.dy)]
    local occupied = cell and cell.visible and cell.monster and ga_call(cell.monster, "attitude") == 0
    if occupied then
      ga_add(actions, {kind="MELEE", dx=move.dx, dy=move.dy, x=move.dx, y=move.dy,
        target_name=tostring(ga_call(cell.monster, "name") or "unknown"),
        label="MELEE "..move.key})
    elseif ga_cell_passable(cell) and not blocked[ga_map_key(move.dx, move.dy)] then
      ga_add(actions, {kind="MOVE", dx=move.dx, dy=move.dy, x=move.dx, y=move.dy,
        label="MOVE "..move.key})
    end
  end

  ga_add(actions, {kind="WAIT", label="WAIT"})
  local here = cells["0:0"]
  local feature = here and tostring(here.feature or "") or ""
  if feature:find("stone_stairs_down", 1, true) then
    ga_add(actions, {kind="TAKE_STAIRS_DOWN", label="STAIRS DOWN"})
  end
  if feature:find("stone_stairs_up", 1, true) then
    ga_add(actions, {kind="TAKE_STAIRS_UP", label="STAIRS UP"})
  end

  if you.floor_items then
    for _, item in ipairs(you.floor_items() or {}) do
      ga_add(actions, {kind="PICKUP", item_name=ga_item_name(item),
        label="PICKUP "..ga_item_name(item)})
    end
  end

  if you.ability_info then
    local info = you.ability_info()
    for _, entry in ipairs(info or {}) do
      -- These abilities open a confirmation menu rather than representing a
      -- single semantic turn.  Keep them out of V1 until the menu adapter can
      -- return an explicit ACCEPT/DECLINE action without stranding the actor.
      local ability_name = tostring(entry[1] or "")
      local destructive = ability_name:find("Renounce", 1, true)
          or ability_name:find("Abandon", 1, true)
      if entry[1] and entry[2] and not destructive then
        ga_add(actions, {kind="USE_ABILITY", name=entry[1],
          x=target and target.x or 0, y=target and target.y or 0,
          label="ABILITY "..entry[1]})
      end
    end
  end

  -- Spell casting is already exposed by Crawl's semantic Lua API.  The
  -- action carries a concrete spell name and target instead of a menu letter.
  if you.spells and spells and spells.cast then
    local known_spells = you.spells() or {}
    for _, spell_name in ipairs(known_spells) do
      local targetable = false
      if spells.target then
        local ok, value = pcall(spells.target, spell_name)
        targetable = ok and value and true or false
      end
      if not targetable or target then
        ga_add(actions, {kind="CAST", name=spell_name,
          x=target and target.x or 0, y=target and target.y or 0,
          label="CAST "..tostring(spell_name)})
      end
    end
  end

  for _, item in ipairs(items.inventory()) do
    local slot = item.slot
    if slot ~= nil then
      local class = ga_item_class(item)
      local name = ga_item_name(item)
      local known = item.is_identified ~= false
      local label = string.sub(name, 1, 48)
      if class == "potion" and known then
        ga_add(actions, {kind="QUAFF", slot=slot, item_name=name, label="QUAFF "..label})
      elseif class == "scroll" and known then
        ga_add(actions, {kind="READ", slot=slot, item_name=name, label="READ "..label})
      elseif class == "wand" and target and item.quantity and item.quantity > 0 then
        ga_add(actions, {kind="FIRE", slot=slot, x=target.x, y=target.y,
          item_name=name, label="FIRE "..label})
      elseif item.is_throwable and target and not ga_you("caught") and not ga_you("berserk") then
        ga_add(actions, {kind="FIRE", slot=slot, x=target.x, y=target.y,
          item_name=name, label="THROW "..label})
      elseif item.equip_type and not item.equipped then
        local equip_kind = class:find("weapon", 1, true) and "WIELD" or "WEAR"
        ga_add(actions, {kind=equip_kind, slot=slot, item_name=name,
          label="EQUIP "..label})
      elseif item.equipped and item.equip_type
          and not class:find("weapon", 1, true) then
        ga_add(actions, {kind="REMOVE", slot=slot, item_name=name,
          label="REMOVE "..label})
      end
    end
  end
  return actions
end

local function ga_player()
  local hp, max_hp = ga_you("hp")
  local mp, max_mp = ga_you("mp")
  local result = {hp=hp, max_hp=max_hp, mp=mp, max_mp=max_mp,
    x=ga_you("x_pos") or 0, y=ga_you("y_pos") or 0, xl=ga_you("xl") or 0,
    species=ga_you("species") or "unknown", class=ga_you("class") or "unknown",
    god=ga_you("god") or "", gold=ga_you("gold") or 0,
    ac=ga_you("ac") or 0, ev=ga_you("ev") or 0, sh=ga_you("sh") or 0,
    strength=ga_you("strength") or 0, intelligence=ga_you("intelligence") or 0,
    dexterity=ga_you("dexterity") or 0, status=ga_you("status") or "",
    confused=ga_you("confused") or false, berserk=ga_you("berserk") or false,
    poisoned=ga_you("poisoned") or false, on_fire=ga_you("on_fire") or false,
    transform=ga_you("transform") or "", safe=ga_you("feel_safe") or false,
    willpower=ga_you("willpower") or 0, see_invisible=ga_you("see_invisible") or 0,
    flying=ga_you("flying") or false, spells=ga_you("spells") or {}}
  for _, resistance in ipairs({"res_poison", "res_fire", "res_cold",
      "res_draining", "res_shock", "res_corr"}) do
    result[resistance] = ga_you(resistance) or 0
  end
  local skills = {"Fighting", "Short Blades", "Long Blades", "Axes",
    "Maces & Flails", "Polearms", "Staves", "Ranged Weapons", "Throwing",
    "Armour", "Dodging", "Stealth", "Shields", "Unarmed Combat", "Spellcasting",
    "Conjurations", "Hexes", "Summonings", "Necromancy", "Translocations",
    "Fire Magic", "Ice Magic", "Air Magic", "Earth Magic", "Alchemy",
    "Invocations", "Evocations", "Shapeshifting"}
  result.skills = {}
  for _, name in ipairs(skills) do
    local ok, value = pcall(you.skill, name)
    if ok then result.skills[name] = value end
  end
  return result
end

local function ga_inventory()
  local result = {}
  for _, item in ipairs(items.inventory()) do
    result[#result+1] = {slot=item.slot, letter=items.index_to_letter(item.slot),
      name=ga_item_name(item), class=ga_item_class(item),
      subtype=tostring(ga_call(item, "subtype", false) or ""),
      quantity=item.quantity, equipped=item.equipped, identified=item.is_identified,
      equip_type=item.equip_type, plus=item.plus, damage=item.damage,
      accuracy=item.accuracy, delay=item.delay, ac=item.ac, ev=item.ev,
      is_ranged=item.is_ranged, is_throwable=item.is_throwable,
      is_xp_evoker=item.is_xp_evoker, reach_range=item.reach_range}
  end
  return result
end

local function ga_floor_items()
  local result = {}
  if you.floor_items then
    for _, item in ipairs(you.floor_items() or {}) do
      result[#result+1] = {name=ga_item_name(item), class=ga_item_class(item),
        quantity=item.quantity, identified=item.is_identified}
    end
  end
  return result
end

local function ga_observation()
  local cells = ga_map()
  local monsters, blocked = ga_enemy_scan(cells)
  local visible_cells, known_cells = {}, {}
  for key, cell in pairs(cells) do
    local value = {x=cell.x, y=cell.y, feature=cell.feature,
      visible=cell.visible, mapped=cell.mapped, traversable=cell.traversable,
      frontier=cell.frontier, excluded=cell.excluded, unsafe=cell.unsafe,
      cloud=cell.cloud, invisible_monster=cell.invisible_monster,
      occupied=cell.visible and cell.monster ~= nil}
    known_cells[key] = value
    if cell.visible then visible_cells[key] = value end
  end
  local hp, max_hp = ga_you("hp")
  local mp, max_mp = ga_you("mp")
  return {schema="crawl-general-v1", seq=GA.seq, turn=ga_you("turns") or 0,
    coordinate_frame="player_relative",
    level=ga_level(), branch=ga_you("branch") or "unknown", depth=ga_you("depth") or 0,
    player=ga_player(), hp={hp, max_hp}, mp={mp, max_mp},
    status=ga_you("status") or "", safe=ga_you("feel_safe") or false,
    monsters=monsters, inventory=ga_inventory(), floor_items=ga_floor_items(), cells=visible_cells,
    known=known_cells, actions=ga_actions(cells, monsters, blocked),
    -- Standard-game non-winning score; old engines explicitly lack this API.
    score=ga_you("game_score") or -1,
    score_status=ga_you("game_score") ~= nil and "live_official" or "unavailable",
    terminal=false, last_action_result=GA.last_action_result}
end

local function ga_publish()
  GA.actions = ga_observation().actions
  GA.published = GA.seq
  crawl.tactical_emit(function()
    local observation = ga_observation()
    observation.actions = GA.actions
    return "GJSON " .. ga_json(observation) .. "\n"
  end)
end

local function ga_find_item(slot)
  for _, item in ipairs(items.inventory()) do
    if item.slot == slot then return item end
  end
  return nil
end

local function ga_dispatch(action)
  if not action then return false end
  if action.kind == "MOVE" or action.kind == "MELEE" then
    for _, move in ipairs(GA_MOVES) do
      if move.dx == action.dx and move.dy == action.dy then
        crawl.do_commands({move.cmd}); return true
      end
    end
  elseif action.kind == "WAIT" then
    crawl.do_commands({"CMD_WAIT"}); return true
  elseif action.kind == "TAKE_STAIRS_DOWN" then
    crawl.do_commands({"CMD_GO_DOWNSTAIRS"}); return true
  elseif action.kind == "TAKE_STAIRS_UP" then
    crawl.do_commands({"CMD_GO_UPSTAIRS"}); return true
  elseif action.kind == "USE_ABILITY" then
    return you.activate_ability(action.name, action.x or 0, action.y or 0, true)
  elseif action.kind == "CAST" then
    return spells.cast(action.name, action.x or 0, action.y or 0, true)
  elseif action.kind == "FIRE" then
    return items.fire(action.slot, action.x or 0, action.y or 0, true)
  elseif action.kind == "WIELD" or action.kind == "WEAR" then
    local item = ga_find_item(action.slot)
    return item and item.equip() or false
  elseif action.kind == "REMOVE" then
    local item = ga_find_item(action.slot)
    return item and item.remove() or false
  elseif action.kind == "QUAFF" then
    crawl.process_keys("q" .. items.index_to_letter(action.slot) .. "\027\027")
    return true
  elseif action.kind == "READ" then
    crawl.process_keys("r" .. items.index_to_letter(action.slot) .. "\027\027")
    return true
  elseif action.kind == "PICKUP" then
    if you.floor_items then
      for _, item in ipairs(you.floor_items() or {}) do
        if ga_item_name(item) == action.item_name then
          return items.pickup(item) and true or false
        end
      end
    end
  end
  return false
end

local function ga_save()
  crawl.do_commands({"CMD_SAVE_GAME_NOW"})
end

function ready()
  -- Let the original hook perform any harmless UI maintenance, but it is
  -- paused before it can spend a gameplay turn.
  ga_parent_ready()
  if not GA.active or ga_you("turn_is_over") then return end
  if GA.published ~= GA.seq then ga_publish() end
  local key = crawl.getch()
  if key == 30 then
    ga_save()
    return
  end
  if key == 27 then return end
  local index = key - 33
  if index >= 0 and index < #GA.actions then
    local action = GA.actions[index + 1]
    local spent = ga_dispatch(action)
    GA.last_action_result = {kind=action.kind, dispatch_accepted=spent and true or false}
    if not spent and not you.turn_is_over() then
      local turn = ga_you("turns")
      if GA.rejected_turn ~= turn then GA.rejected_actions = {} end
      GA.rejected_turn = turn
      GA.rejected_actions = GA.rejected_actions or {}
      local key = table.concat({action.kind or "", action.slot or "", action.name or "",
        action.x or "", action.y or "", action.dx or "", action.dy or "", action.item_name or ""}, "|")
      GA.rejected_actions[key] = true
    end
    -- Stairs/equipment may start an engine delay without immediately spending
    -- a turn. Wake the outer command loop with a no-turn escape so it can
    -- advance that delay instead of blocking on terminal input.
    if not you.turn_is_over() then crawl.sendkeys("\027") end
    if spent or you.turn_is_over() then
      GA.seq = GA.seq + 1
      GA.published = -1
    else
      -- Report rejection without silently executing a different game action.
      GA.seq = GA.seq + 1
      GA.published = -1
    end
  end
end
