local function upvalue(fn,wanted,seen)
  seen=seen or {}; if seen[fn] then return end; seen[fn]=true
  for i=1,100 do
    local n,v=debug.getupvalue(fn,i); if not n then break end
    if n==wanted then return v end
    if type(v)=="function" then local r=upvalue(v,wanted,seen); if r then return r end end
  end
end
local turn,hp,berserk,poison=1,40,false,false
local commands,inventory,statuses={},{},{}
you={turns=function() return turn end,hp=function() return hp,100 end,
  berserk=function() return berserk end,confused=function() return false end,
  silenced=function() return false end,poisoned=function() return poison end,
  poison_survival=function() return 5 end,status=function(s) return statuses[s] end,
  ability_info=function() return nil end,intelligence=function() return 4 end}
items={inventory=function() return inventory end,index_to_letter=function() return "a" end}
crawl.mpr=function() end
crawl.process_keys=function(s) commands[#commands+1]=s; turn=turn+1 end
local function consumable(kind,name,known)
 return {slot=0,is_identified=known,class=function() return kind end,name=function() return name end}
end
local survival=assert(upvalue(ready,"survival_action"))
local scan={any=true,monsters={{}},reachable_worst=1,worst=1}
inventory={consumable("potion","potion of heal wounds",true)}
assert(survival(scan) and commands[1]=="qa\027\027\027","heal before continuing combat")
turn=turn+1
you.turn_is_over=function() return true end
crawl.process_keys=function(s) commands[#commands+1]=s end
assert(survival(scan),"a spent turn must end the hook even before turns() increments")
you.turn_is_over=nil
crawl.process_keys=function(s) commands[#commands+1]=s; turn=turn+1 end
berserk=true; commands={}
assert(not survival(scan) and #commands==0,"do not attempt consumables while berserk")
berserk=false; hp=60; poison=true
inventory={consumable("potion","potion of curing",true)}
assert(survival({any=false}) and commands[1]=="qa\027\027\027","cure lethal poison even out of combat")
poison=false; hp=40; commands={}
inventory={consumable("scroll","scroll of teleportation",true)}
assert(survival(scan) and commands[1]=="ra\027\027\027")
statuses["about to teleport"]=true; commands={}
assert(not survival(scan) and #commands==0,"do not cancel pending teleport with another scroll")
local safe=assert(upvalue(ready,"safe_stats"))
assert(not safe({artprops={Int=-4}}),"reject stat-zero armour")
assert(safe({artprops={Int=-2}}),"allow safe negative modifier")
you.intelligence=function() return 0 end
assert(not safe({artprops={Int=-4},equipped=true}),"recover from already worn stat-zero gear")
print("survival regression cases passed")
