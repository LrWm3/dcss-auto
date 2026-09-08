local function find(fn,wanted,seen)
  seen=seen or {}; if seen[fn] then return end; seen[fn]=true
  for i=1,100 do
    local n,v=debug.getupvalue(fn,i); if not n then break end
    if n==wanted then return v end
    if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
  end
end
local action=assert(find(ready,"throwing_action"))
local bot=BOT
local turn=100
you={transform=function() return "" end,turns=function() return turn end,berserk=function() return false end,
 confused=function() return false end,slowed=function() return false end,
 exhausted=function() return false end,status=function() return false end,
 turn_is_over=function() return true end}
local m={name=function() return "ogre" end,res_poison=function() return 0 end,
 status=function() return false end}
local scan={worst=2,monsters={{x=3,y=0,threat=2,reachable=true,monster=m}},cells={}}
for x=0,3 do scan.cells[x..":0"]={visible=true,traversable=true} end
local function ammo(n,slot) return {slot=slot,class=function() return "missile" end,
 name=function() return n end} end
items={inventory=function() return {ammo("boomerang",0),ammo("curare-tipped dart",1)} end,
 index_to_letter=function(s) return s==0 and "a" or "b" end}
local keys
crawl.process_keys=function(k) keys=k end
crawl.mpr=function() end; crawl.take_note=function() end
bot.encounter={phase="prepare"}
assert(action(scan)); assert(keys=="Farlllf\027\027\027")
assert(not action(scan),"same turn blocked")
turn=101; scan.worst=3; scan.monsters[1].threat=3
assert(action(scan)); assert(keys=="Fbrlllf\027\027\027")
turn=102; m.status=function(_,s) return s=="poisoned" end
assert(action(scan)); assert(keys=="Farlllf\027\027\027")
turn=103; assert(not action(scan),"three total throws cap")
bot.encounter={phase="disengage"}; assert(not action(scan))
bot.encounter={phase="prepare"}
scan.cells["1:0"].monster={}; assert(not action(scan),"blocked shot")
scan.cells["1:0"].monster=nil
scan.monsters[2]={x=1,y=1,threat=0}; assert(not action(scan),"any adjacent hostile")
print("throwing regression cases passed")
