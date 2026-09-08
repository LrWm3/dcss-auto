local function find(fn,wanted,seen)
  seen=seen or {}; if seen[fn] then return end; seen[fn]=true
  for i=1,100 do
    local n,v=debug.getupvalue(fn,i); if not n then break end
    if n==wanted then return v end
    if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
  end
end
local observe=assert(find(ready,"observe_steam_dragon"))
local act=assert(find(ready,"steam_charge_action"))
local turn,px=1,0
you={turns=function() return turn end,hp=function() return 50,56 end,
 branch=function() return "D" end,depth=function() return 7 end,
 confused=function() return false end,status=function() return false end,
 transform=function() return "" end}
travel={waypoint_delta=function() return px,0 end}
BOT.recovery_anchor={level="D:7"}
view={is_safe_square=function(x,y) return x~=1 end}
local last
crawl.mpr=function() end; crawl.take_note=function() end
crawl.sendkeys=function(k) last=k end
local dragon={name=function() return "steam dragon" end}
local scan={monsters={{x=3,y=0,monster=dragon}},cells={},blocked={["3:0"]=true}}
for x=0,3 do scan.cells[x..":0"]={x=x,y=0,traversable=true,feature="floor",visible=true} end
scan.cells["1:0"].cloud="steam"; scan.cells["1:0"].unsafe=true
scan.cells["3:0"].monster=dragon
observe(scan)
assert(act(scan) and last=="l","charge visible dragon through steam")
scan.monsters={}; scan.cells["3:0"].monster=nil; scan.blocked={}; turn=2
observe(scan)
assert(act(scan) and last=="l","charge last-seen position while obscured")
assert(scan.cells["1:0"].unsafe,"steam exception cannot mutate shared safety map")
scan.cells["1:0"].cloud="poison gas"
assert(not act(scan),"never extend steam exception to other clouds")
scan.monsters={{x=3,y=0,monster=dragon}}; observe(scan)
scan.cells["1:0"].cloud="steam"; scan.cells["1:0"].excluded=true
assert(not act(scan),"respect exclusions")
scan.cells["1:0"].excluded=nil; scan.monsters={}; turn=20; observe(scan)
assert(not BOT.steam_target and not act(scan),"expire stale sightings")
turn=21; scan.monsters={{x=3,y=0,monster=dragon}}; observe(scan)
scan.monsters={}; BOT.steam_target.steps=8
assert(not act(scan),"bound hidden pursuit steps")
observe({monsters={{x=3,y=0,monster=dragon}}}); px=3
assert(not act(scan),"stop when last known square is reached")
px=0; observe(scan); BOT.steam_target={level="D:6",x=3,y=0,seen=turn,steps=0}
assert(not act(scan),"no cross-floor pursuit")
print("steam charge regression cases passed")
