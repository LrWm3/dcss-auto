-- Regression cases against the actual local RC functions (Lua test runtime).
local function find_upvalue(fn, wanted, seen)
  seen = seen or {}
  if seen[fn] then return end
  seen[fn] = true
  for i=1,100 do
    local name, value = debug.getupvalue(fn, i)
    if not name then break end
    if name == wanted then return value end
    if type(value) == "function" then
      local found = find_upvalue(value, wanted, seen)
      if found then return found end
    end
  end
end
local commands = {}
view = {}
crawl.mpr = function() end
crawl.sendkeys = function(s) commands[#commands+1] = s end
crawl.process_keys = crawl.sendkeys
crawl.do_commands = function(cs)
  assert(#cs == 1)
  commands[#commands+1] = cs[1]
end
you = {berserk=function() return false end, exhausted=function() return false end,
  hp=function() return 100,100 end,
  slowed=function() return false end,
  activate_ability=function(name) commands[#commands+1]=name; return true end}
local encounter = assert(find_upvalue(ready, "encounter_action"))
for _, threat in ipairs({2,3,4}) do
  commands = {}
  encounter({any=true,worst=threat,reachable_any=true,yellow_adjacent=threat==2,
    monsters={{x=1,y=0,reachable=true,threat=threat}}})
  assert(commands[1] == "Berserk", "red and yellow must share berserk policy")
end
commands = {}
BOT.autofight_rejected = true
encounter({any=true,worst=3,reachable_any=true,
  monsters={{x=1,y=0,reachable=true,threat=3}}})
assert(commands[1] == "CMD_MOVE_RIGHT", "rejected Tab must fall back to a real step")

local cells = {
  ["0:0"]={x=0,y=0,traversable=true,feature="floor"},
  ["1:0"]={x=1,y=0,traversable=true,feature="enter_shop",unvisited=true}}
commands = {}
assert(find_upvalue(ready,"visit_shop_action")({cells=cells,blocked={}}))
assert(commands[1] == "l", "visit a known unvisited shop before native exploration")
cells["1:0"].unvisited = false
assert(not find_upvalue(ready,"visit_shop_action")({cells=cells,blocked={}}))

local stairs = find_upvalue(ready,"count_down_cycle_targets")
view = {get_map=function() return {
  {x=3,y=1,feature="stone_stairs_down_ii"},
  {x=-2,y=4,feature="stone_stairs_down_i"},
  {x=-5,y=0,feature="escape_hatch_down"}} end}
local targets=stairs()
assert(#targets==2 and targets[1].x==-2 and targets[2].x==3)

local worn, equipped_count = nil, 0
local function armour(name, subtype, ac, plus)
  local it={ac=ac,plus=plus,is_identified=true}
  it.name=function() return name end
  it.class=function() return "armour" end
  it.subtype=function() return subtype end
  it.ego=function() return false end
  it.equip=function()
    assert(subtype=="body", "auxiliary must not remove Lear's hauberk")
    worn=it; it.equipped=true; equipped_count=equipped_count+1; return true
  end
  return it
end
local lear=armour("+18 Lear's hauberk","body",10,18)
local hat=armour("-2 hat","helmet",0,-2)
items={inventory=function() return {hat,lear} end,
  equipped_at=function(slot) if slot=="Armour" then return worn end end}
local equip=assert(find_upvalue(ready,"auto_equip_action"))
for i=1,10 do equip() end
assert(equipped_count==1, "hauberk gear plan must settle")
local potion={slot=3,quantity=2,is_identified=false,class=function() return "potion" end}
items.inventory=function() return {potion} end
items.index_to_letter=function(slot) return string.char(97+slot) end
BOT.blind_pending=true
BOT.blind_target="d"
commands={}
c_message("It was a scroll of vulnerability.")
assert(not BOT.blind_pending and BOT.blind_target==nil)
BOT.blind_pending=true
BOT.blind_target="d"
c_message("As you read the scroll of identify, it crumbles to dust.")
assert(#commands==0, "identify message must never queue a second target key")
assert(c_choose_identify()=="d", "identify hook selects an unknown potion")
assert(not BOT.blind_pending and BOT.blind_target==nil)
local auto_id = assert(find_upvalue(ready,"auto_id_action"))
view.feature_at=function() return "stone_stairs_up_i" end
you.confused=function() return false end
you.silenced=function() return true end
commands={}
assert(not auto_id() and #commands==0, "silence must not queue scroll reading")
you.silenced=function() return false end
local scroll={slot=2,quantity=2,is_identified=false,class=function() return "scroll" end}
items.inventory=function() return {scroll,potion} end
assert(auto_id() and commands[1]=="rc\027\027\027", "reading resumes with menu guards when silence ends")
commands={}
BOT.blind_pending=true
c_message("Blink to where?")
assert(#commands==0, "guarded blind blink must not leak target keys into normal commands")
assert(c_answer_prompt("Are you sure you want to cancel this blink?")==true)
BOT.blind_pending=false

local step=assert(find_upvalue(ready,"can_step"))
view.is_safe_square=function(x,y) return x~=1 end
assert(not step({["1:0"]={x=1,y=0,feature="trap_teleport",traversable=true}},
  0,0,1,0,{}), "known offscreen trap must not become a safe BFS route")
view.is_safe_square=nil
you.branch=function() return "D" end
you.depth=function() return 2 end
BOT.dive={phase="normal"}
BOT.committed_entry={parent="D:2",child="D:3",index=2}
find_upvalue(ready,"check_committed_return")()
assert(BOT.failed_entries["D:2"][2] and not BOT.committed_entry)
BOT.dive={phase="survey_parent",parent="D:2",index=2,total=2,reachable={1}}
view.get_map=function() return {{x=0,y=0,feature="stone_stairs_down_i",traversable=true}} end
view.feature_at=function() return "stone_stairs_down_i" end
BOT.dive.commit_pos=1
commands={}
assert(find_upvalue(ready,"dive_action")())
assert(BOT.dive.index==3 and commands[1]==">", "failed stair must be skipped for another entry")
BOT.dive={phase="survey_parent",parent="D:2",index=1,total=0,reachable={}}
view.get_map=function() return {
  {x=0,y=0,feature="floor",traversable=true},
  {x=0,y=1,feature="stone_stairs_up_i",traversable=true}} end
view.feature_at=function() return "floor" end
commands={}
assert(find_upvalue(ready,"dive_action")())
assert(commands[1]=="j" and BOT.dive.phase=="normal" and BOT.floor_partial["D:2"],
  "exhausted survey must actually retreat before native exploration can restart")
commands={}
c_message("Spend multiple turns changing equipment while enemies are nearby?")
assert(commands[1]=="N", "decline equipment delays during combat")
you.feel_safe=function() return false end
assert(not equip(), "do not start changing gear when Crawl reports danger")
local escape_cloud=assert(find_upvalue(ready,"unsafe_square_action"))
view.is_safe_square=function(x,y) return x==1 and y==0 end
commands={}
assert(escape_cloud({cells={
  ["0:0"]={x=0,y=0,feature="floor",traversable=true},
  ["1:0"]={x=1,y=0,feature="floor",traversable=true}},blocked={}}))
assert(commands[1]=="l", "leave harmful cloud for a safe adjacent tile")
view.is_safe_square=function() return false end
commands={}
assert(escape_cloud({cells={},blocked={}}) and commands[1]=="CMD_WAIT",
  "trapped in cloud must spend a turn instead of repeating native explore")
commands={}
local cloud_scan={any=true,worst=1,reachable_any=false,monsters={{x=2,y=0}},blocked={["2:0"]=true},
  cells={["0:0"]={x=0,y=0,feature="floor",traversable=true},
    ["1:0"]={x=1,y=0,feature="floor",traversable=true,cloud="steam",unsafe=true}}}
encounter(cloud_scan)
assert(commands[1]=="CMD_WAIT", "temporary cloud barrier must not trigger exploration pause")
commands={}
cloud_scan.monsters={{x=5,y=0}}
cloud_scan.cells["1:0"].traversable=false
BOT.custom_exploring_level=nil
encounter(cloud_scan)
assert(commands[1]~="CMD_WAIT", "sealed-vault cloud must not cause blanket waiting")
commands={}
c_message("Really equip i - the +11 war axe of Bread {speed, Bane}?")
assert(commands[1]=="Y", "selected gear warning prompt must be answered")
print("autonomous regression cases passed")
