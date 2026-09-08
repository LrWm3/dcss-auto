-- Experimental encounter-only policy. Insert inside the canonical Lua block.
-- MODEL_Q is emitted by export_model.py; no policy is inferred in this file.
ML_EUSTACHIO=ML_EUSTACHIO or {seen=false,active=false}
local ml_previous_ready=ready
local ml_previous_save=c_save
function c_save()
  return ml_previous_save().."\nML_EUSTACHIO="..route_serialize(ML_EUSTACHIO).."\n"
end
local function ml_note(message)
  say("learned Eustachio: "..message)
  crawl.take_note("learned Eustachio: "..message)
end
local function ml_handoff(reason)
  ML_EUSTACHIO.active=false
  ml_note("handoff "..reason)
  ml_previous_ready()
end
function ready()
  if you.species()~="Minotaur" or you.class()~="Berserker"
      or BOT.paused or AUTOCrawl_DEBUG_STATE.paused then ml_previous_ready();return end
  if ML_EUSTACHIO.seen and not ML_EUSTACHIO.active then ml_previous_ready();return end
  local scan=scan_hostiles()
  local t=ML_EUSTACHIO
  if not t.seen then
    for _,e in ipairs(scan.monsters) do
      if e.monster:name():lower()=="eustachio" then
        t.seen=true;t.active=true;t.floor=level_key();t.decisions=0;t.noops=0
        ml_note("activate")
        break
      end
    end
  end
  if not t.active then ml_previous_ready();return end
  if t.floor~=level_key() then ml_handoff("floor changed");return end
  t.noops=t.last_turn==you.turns() and t.noops+1 or 0
  t.last_turn=you.turns()
  if t.noops>=8 or t.decisions>=240 then ml_handoff("budget or no-turn guard");return end
  local hp,mhp=you.hp()
  if not scan.any and you.feel_safe() and hp>=mhp and you.status()==""
      and not you.poisoned() and not you.on_fire() then
    t.safe_since=t.safe_since or you.turns()
    if you.turns()-t.safe_since>=10 then ml_handoff("safe recovery");return end
  else t.safe_since=nil end
  local distance=9
  for _,e in ipairs(scan.monsters) do distance=math.min(distance,math.max(math.abs(e.x),math.abs(e.y))) end
  local k=table.concat({math.min(4,math.floor(5*hp/mhp)),math.min(3,#scan.monsters),
    math.min(3,distance),tostring(you.berserk()),tostring(berserk_recovering()),
    tostring(you.status()~="")},"|")
  local scores=MODEL_Q[k]
  if not scores then ml_handoff("unseen model state");return end
  local choices={"wait"}
  if scan.any then
    choices[#choices+1]="tab";choices[#choices+1]="retreat"
    if not you.berserk() and not berserk_recovering() and not you.confused() then
      choices[#choices+1]="berserk"
    end
  end
  local selected,best=nil,-math.huge
  for _,a in ipairs(choices) do
    local score=scores[a] or 0
    if score>best then selected=a;best=score end
  end
  if selected=="retreat" then ml_handoff("unsupported retreat option");return end
  t.decisions=t.decisions+1
  if t.last_action~=selected then ml_note("action "..selected);t.last_action=selected end
  if selected=="berserk" then
    if not you.activate_ability("Berserk",0,0) then ml_handoff("berserk unavailable") end
  else crawl.do_commands({selected=="tab" and "CMD_AUTOFIGHT" or "CMD_WAIT"}) end
end
