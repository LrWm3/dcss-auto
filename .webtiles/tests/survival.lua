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
turn=turn+1; commands={}
inventory={consumable("scroll","scroll of fear",true)}
scan.monsters={{},{}}
assert(survival(scan) and commands[1]=="raf\027\027\027",
  "confirm known fear area preview before escape guards")
scan.monsters={{}}
local use=assert(upvalue(ready,"use_known_consumable"))
turn=turn+1; commands={}
inventory={consumable("potion","potion of invisibility",true)}
assert(use("potion","invisibility") and commands[1]=="qaf\027\027\027",
  "confirm invisibility preview before cancellation guards")
local safe=assert(upvalue(ready,"safe_stats"))
assert(not safe({artprops={Int=-4}}),"reject stat-zero armour")
assert(safe({artprops={Int=-2}}),"allow safe negative modifier")
you.intelligence=function() return 0 end
assert(not safe({artprops={Int=-4},equipped=true}),"recover from already worn stat-zero gear")

local rage=assert(upvalue(ready,"should_berserk"))
you.exhausted=function() return false end
you.slowed=function() return false end
hp=100; berserk=false
local crowd={yellow_adjacent=false,reachable_adjacent=true,monsters={{},{},{}}}
assert(rage(crowd),"default policy retains crowd berserk")
AUTOCrawl_TACTICS.crowd_berserk=false
assert(not rage(crowd),"crowd policy is independently configurable")
crowd.yellow_adjacent=true
assert(rage(crowd),"yellow-adjacent rule remains independent of crowd switch")
hp=54; assert(not rage(crowd),"default berserk HP floor is unchanged")
hp=55; assert(rage(crowd),"berserk HP boundary is inclusive")
you.exhausted=function() return true end
assert(not rage(crowd),"exhaustion blocks berserk")
local spent=assert(upvalue(ready,"turn_spent"))
you.turn_is_over=function() return false end
assert(not spent(turn) and spent(turn-1),"turn counter fallback")
you.turn_is_over=function() return true end
assert(spent(turn),"turn flag prevents second command before counter changes")
print("survival regression cases passed")
