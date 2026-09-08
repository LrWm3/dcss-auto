local function find(fn,wanted,seen)
  seen=seen or {}; if seen[fn] then return end; seen[fn]=true
  for i=1,100 do
    local n,v=debug.getupvalue(fn,i); if not n then break end
    if n==wanted then return v end
    if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
  end
end
local observe=assert(find(ready,"observe_encounter"))
local manage=assert(find(ready,"manage_encounter"))
local survival=assert(find(ready,"survival_action"))
local rage=assert(find(ready,"should_berserk"))
local turn,hp,slow,depth=1,100,false,2
you={turns=function() return turn end,hp=function() return hp,100 end,
  branch=function() return "D" end,depth=function() return depth end,
  slowed=function() return slow end,exhausted=function() return slow end,
  berserk=function() return false end,confused=function() return false end,
  silenced=function() return false end,poisoned=function() return false end,
  status=function() return false end,transform=function() return "" end,
  ability_info=function() return {} end}
crawl.mpr=function() end
local commands={}
crawl.do_commands=function(cs) commands[#commands+1]=cs[1] end
crawl.process_keys=function(k) commands[#commands+1]=k; turn=turn+1 end
items={inventory=function() return {} end,index_to_letter=function() return "a" end}
local scan={any=true,monsters={{x=3,y=0,reachable=true}},worst=1,
  reachable_adjacent=false,cells={},blocked={}}
observe(scan); assert(BOT.encounter.phase=="prepare")
scan.reachable_adjacent=true; observe(scan); assert(BOT.encounter.phase=="fight")
slow=true; observe(scan); assert(BOT.encounter.phase=="disengage")
assert(not rage(scan),"do not commit berserk during disengagement")
scan.any=false; scan.monsters={}; scan.reachable_adjacent=false
observe(scan); assert(BOT.encounter.phase=="recover")
assert(manage(scan) and commands[#commands]=="CMD_WAIT","recover without exploring")
slow=false; turn=20; observe(scan); assert(BOT.encounter.phase=="idle")
BOT.disturbance_warning=true; BOT.disturbance_last_seen=turn
hp=40; observe(scan)
assert(BOT.encounter.active and BOT.encounter.unseen and BOT.encounter.phase=="disengage")
items.inventory=function() return {{slot=0,is_identified=true,
  class=function() return "scroll" end,name=function() return "scroll of teleportation" end}} end
assert(survival(scan) and commands[#commands]=="ra\027\027\027",
  "unseen attacker must not bypass known emergency teleport")
assert(not manage(scan),"unseen combat must reach disturbance handling, not blind resting")
BOT.disturbance_warning=false; depth=3; hp=100; observe(scan)
assert(BOT.encounter.phase=="idle" and BOT.encounter.peak==0,"reset on level change")
AUTOCrawl_TACTICS.encounter_control=false; observe(scan)
assert(BOT.encounter==nil,"legacy policy remains selectable")
print("encounter regression cases passed")
