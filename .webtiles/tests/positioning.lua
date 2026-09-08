local function find(fn,wanted,seen)
  seen=seen or {}; if seen[fn] then return end; seen[fn]=true
  for i=1,100 do
    local n,v=debug.getupvalue(fn,i); if not n then break end
    if n==wanted then return v end
    if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
  end
end
local action=assert(find(ready,"positioning_action"))
local hp=100
you={hp=function() return hp,100 end,berserk=function() return false end,
  confused=function() return false end,transform=function() return "" end,
  status=function() return false end,branch=function() return "D" end,depth=function() return 2 end}
local commands={}
crawl.mpr=function() end
crawl.sendkeys=function(k) commands[#commands+1]=k end
crawl.do_commands=function(cs) commands[#commands+1]=cs[1] end
view={is_safe_square=function() return true end}
local cells={}
for x=-3,3 do for y=-3,3 do
  cells[x..":"..y]={x=x,y=y,feature="rock_wall",traversable=false,visible=true}
end end
local function floor(x,y)
  local c=cells[x..":"..y]; c.feature="floor"; c.traversable=true
end
floor(-2,0); floor(-1,0); floor(0,0)
for y=-1,1 do floor(0,y); floor(1,y) end
local scan={cells=cells,blocked={},monsters={},reachable_adjacent=false}
for i=1,3 do scan.monsters[i]={x=i+3,y=0,monster={spells=function() return {} end}} end
assert(action(scan) and commands[1]=="h","retreat toward narrower terrain, not enemies")
BOT.positioning=nil; commands={}; cells["-1:0"].unsafe=true
action(scan)
assert(commands[1]~="h","hazardous retreat tile is rejected even if another exit exists")
cells["-1:0"].unsafe=nil
scan.reachable_adjacent=true
assert(not action(scan),"do not walk away from adjacent attackers")
scan.reachable_adjacent=false
for _,c in pairs(cells) do c.feature="rock_wall"; c.traversable=false end
floor(0,0); floor(1,0); floor(2,0)
BOT.positioning={level="D:2",moves=6,waits=0}
commands={}
for i=1,3 do assert(action(scan)) end
assert(not action(scan) and #commands==3,"holding a choke has a strict wait budget")
BOT.positioning.waits=0; BOT.positioning.hp=100; hp=95
assert(not action(scan),"taking ranged damage cancels holding")
hp=100; scan.monsters[1].monster.spells=function() return {"Magic Dart"} end
assert(not action(scan),"do not wait for casters")
scan.monsters[1].monster.spells=function() return {} end
cells["0:1"]=nil
assert(not action(scan),"unknown terrain is not a wall or a proven choke")
print("positioning regression cases passed")
