-- Appended INSIDE the canonical RC's Lua block: reuse its player-visible scan.
local tb_original_ready = ready
local tb_original_save = c_save
TB = TB or {active=false, seq=0}
AUTOCrawl_TACTICS.debug_encounters=true
AUTOCrawl_DEBUG_NAMES=TB_CAPTURE and {} or {eustachio=true}

local function json(v)
  if type(v)=="string" then
    return '"'..v:gsub('[%z\1-\31\\"]', function(c)
      return string.format('\\u%04x',string.byte(c)) end)..'"'
  elseif type(v)=="number" or type(v)=="boolean" then return tostring(v)
  elseif type(v)=="table" then
    local a={}
    for k,x in pairs(v) do a[#a+1]=json(tostring(k))..":"..json(x) end
    table.sort(a)
    return "{"..table.concat(a,",").."}"
  end
  return "null"
end

function tactical_dump()
  local scan=scan_hostiles()
  local hp,maxhp=you.hp()
  local state={seq=TB.seq,turn=you.turns(),floor=level_key(),hp=hp,max_hp=maxhp,
    berserk=you.berserk(),confused=you.confused(),status=you.status(),
    safe=you.feel_safe(),poisoned=you.poisoned(),on_fire=you.on_fire(),
    cooldown=berserk_recovering(),messages=TB.messages or {},
    monsters={},inventory={},cells={}}
  for i,e in ipairs(scan.monsters) do
    state.monsters[i]={name=e.monster:name(),x=e.x,y=e.y,threat=e.threat,
      reachable=e.reachable}
  end
  for i,it in ipairs(items.inventory()) do
    state.inventory[i]={letter=inv_letter(it),name=item_name(it),class=item_class(it)}
  end
  for k,c in pairs(scan.cells) do
    -- Only currently visible terrain, no hidden engine entities.
    if c.visible then state.cells[k]={x=c.x,y=c.y,feature=c.feature,
      cloud=c.cloud,traversable=c.traversable,invisible_monster=c.invisible_monster} end
  end
  return "\nTBJSON "..json(state).."\n"
end

function c_save()
  return tb_original_save().."\nBOT="..route_serialize(BOT)
    .."\nTB="..route_serialize(TB).."\n"
end

function tb_request(action)
  assert(TB.active,"checkpoint not active")
  assert(not TB.pending,"action already pending")
  TB.pending=action
  TB.messages={}
  crawl.mpr("TBACCEPT END")
end

local tb_previous_message=c_message
function c_message(message,channel)
  if tb_previous_message then tb_previous_message(message,channel) end
  if TB.active and not tostring(message):find("TB",1,true) then
    TB.messages=TB.messages or {}
    if #TB.messages<50 then TB.messages[#TB.messages+1]=tostring(message) end
  end
end

local function publish()
  crawl.dump_char()
  crawl.mpr("TBREADY "..TB.seq.." END")
end

function ready()
  if not TB.active then
    -- Configurable visible first-contact boundary, before the controller acts.
    -- Floor/turn gates avoid collecting unrelated earlier members of a species.
    if TB_CAPTURE and level_key()==TB_CAPTURE.floor
        and you.turns()>=(TB_CAPTURE.min_turn or 0) then
      local scan=scan_hostiles()
      for _,e in ipairs(scan.monsters) do
        if e.monster:name():lower()==TB_CAPTURE.monster:lower() then
          TB.active=true; TB.seq=0; TB.reported=0; publish(); return
        end
      end
    end
    tb_original_ready()
    if AUTOCrawl_DEBUG_STATE.paused then
      TB.active=true; TB.seq=0; TB.reported=0; publish()
    end
    return
  end
  if TB.pending then
    local action=TB.pending
    TB.pending=nil; TB.seq=TB.seq+1; TB.reported=nil
    if action=="baseline" then
      BOT.paused=false; AUTOCrawl_DEBUG_STATE.paused=false
      tb_original_ready()
    elseif action=="berserk" then you.activate_ability("Berserk",0,0)
    else crawl.do_commands({action}) end
    return
  end
  if TB.reported~=TB.seq then TB.reported=TB.seq; publish() end
end
