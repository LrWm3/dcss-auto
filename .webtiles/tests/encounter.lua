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
you.xl=function() return 2 end
AUTOCrawl_TACTICS.early_commit=true
scan.worst=2; hp=40; slow=false
assert(rage(scan),"early adjacent threat may require commitment when escape fails")
slow=true
assert(not rage(scan),"emergency commitment cannot bypass cooldown")
slow=false; hp=19
assert(not rage(scan),"emergency commitment has its own HP floor")
you.xl=function() return 5 end
hp=40
assert(not rage(scan),"early-game override must not leak to higher levels")
you.xl=nil; hp=100; slow=true; scan.worst=1
AUTOCrawl_TACTICS.early_commit=false
scan.any=false; scan.monsters={}; scan.reachable_adjacent=false
observe(scan); assert(BOT.encounter.phase=="recover")
assert(manage(scan) and commands[#commands]=="CMD_WAIT","recover without exploring")
slow=false; turn=20; observe(scan); assert(BOT.encounter.phase=="idle")
you.status=function(s) return s=="on berserk cooldown" end
observe(scan); assert(BOT.encounter.phase=="recover","cooldown is distinct from exhaustion/slow")
assert(manage(scan),"wait out actual berserk cooldown before exploring")
you.status=function() return false end
observe(scan); assert(BOT.encounter.phase=="idle")
BOT.disturbance_warning=true; BOT.disturbance_last_seen=turn
hp=40; observe(scan)
assert(BOT.encounter.active and BOT.encounter.unseen and BOT.encounter.phase=="disengage")
items.inventory=function() return {{slot=0,is_identified=true,
  class=function() return "scroll" end,name=function() return "scroll of teleportation" end}} end
assert(survival(scan) and commands[#commands]=="ra\027\027\027",
  "unseen attacker must not bypass known emergency teleport")
assert(not manage(scan),"unseen combat must reach disturbance handling, not blind resting")
you.mesmerised=function() return true end
scan.any=true; scan.monsters={{x=3,y=0,reachable=true}}
assert(not manage(scan),"mesmerism must delegate to combat, not retreat")
you.mesmerised=function() return false end
scan.any=false; scan.monsters={}
BOT.disturbance_warning=false; depth=3; hp=100; observe(scan)
assert(BOT.encounter.phase=="idle" and BOT.encounter.peak==0,"reset on level change")
AUTOCrawl_TACTICS.encounter_control=false; observe(scan)
assert(BOT.encounter==nil,"legacy policy remains selectable")
AUTOCrawl_TACTICS.encounter_control=true
BOT.disturbance_warning=false; hp=100; turn=100
scan.any=true; scan.worst=2; scan.reachable_adjacent=true
scan.monsters={{x=1,y=0,reachable=true,threat=2,monster={
  name=function() return "Sigmund" end,spells=function() return {"Invisibility","Confuse"} end}}}
observe(scan); assert(BOT.encounter.hidden_caster.name=="Sigmund")
local used
you.ability_info=function() return {{"Trog's Hand",true,"b"}} end
you.activate_ability=function(name) used=name; return true end
items.inventory=function() return {} end
assert(survival(scan) and used=="Trog's Hand","prebuff at full HP before caster disappears")
scan.monsters={{x=1,y=0,reachable=true,threat=1}}; scan.worst=1; turn=101
observe(scan)
assert(BOT.encounter.hidden_missing and BOT.encounter.unseen,
  "other visible hostiles do not erase remembered invisible caster")
assert(not rage(scan),"unresolved invisible caster vetoes berserk")
c_message("You kill Sigmund!","plain")
assert(not BOT.encounter.hidden_caster,"confirmed death clears threat memory")
scan.monsters={{x=1,y=0,reachable=true,threat=2,monster={
  name=function() return "Sigmund" end,spells=function() return {"Invisibility"} end}}}
scan.reachable_any=true; scan.any=true; hp=60; turn=110
observe(scan)
local combat=assert(find(ready,"combat_action"))
crawl.do_commands=function(cs)
  assert(#cs==1 and cs[1]=="CMD_ATTACK_RIGHT","one directed caster attack, no gsub count")
end
assert(combat(scan),"remembered adjacent caster receives the attack")
print("encounter regression cases passed")
