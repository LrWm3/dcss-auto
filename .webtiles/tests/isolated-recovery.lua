local function find(fn,wanted,seen)
  seen=seen or {}; if seen[fn] then return end; seen[fn]=true
  for i=1,100 do
    local n,v=debug.getupvalue(fn,i); if not n then break end
    if n==wanted then return v end
    if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
  end
end
local observe=assert(find(ready,"observe_recovery_anchor"))
local act=assert(find(ready,"isolated_recovery_action"))
local hp,depth,px,py,range=32,6,0,0,1
you={hp=function() return hp,71 end,branch=function() return "D" end,
 depth=function() return depth end,berserk=function() return false end,
 status=function() return false end,slowed=function() return false end,
 exhausted=function() return false end}
view={feature_at=function() return "stone_stairs_up_i" end}
travel={set_waypoint=function(n,x,y) assert(n==9 and x==0 and y==0); px=0; py=0 end,
 waypoint_delta=function(n) assert(n==9); return px,py end}
local last
crawl.mpr=function() end
crawl.sendkeys=function(k) last=k end
crawl.do_commands=function(c) last=c[1] end
local scan={any=true,reachable_any=false,monsters={{monster={range=function() return range end}}},
 cells={},first_step={}}
observe(scan)
assert(BOT.recovery_anchor.stairs)
BOT.encounter={phase="disengage",retreats=6}
px=8
scan.cells["-8:0"]={x=-8,y=0,feature="floor",traversable=true}
scan.first_step["-8:0"]="h"
assert(act(scan) and last=="h","return toward arrival stairs, not exploration")
scan.cells["-8:0"].visible=true
assert(act(scan) and last=="CMD_WAIT","heal with anchor visible and isolated bear")
hp=60; BOT.encounter.phase="prepare"
assert(act(scan) and last=="CMD_WAIT","recovery latch survives phase change at65percent")
scan.any=false; scan.monsters={}
assert(act(scan) and last=="CMD_WAIT","enemy leaving LOS cannot restart exploration")
hp=71; assert(not act(scan) and not BOT.isolated_recovering)
hp=32; scan.any=true; scan.monsters={{monster={range=function() return range end}}}
BOT.recovery_anchor.stairs=nil
BOT.recovery_anchor.rest={x=4,y=0}
scan.cells["-4:0"]={x=-4,y=0,feature="floor",traversable=true}
scan.first_step["-4:0"]="y"
assert(act(scan) and last=="y","rest anchor precedes entry fallback; delta sign correct")
scan.cells["-4:0"]=nil
assert(act(scan) and last=="CMD_WAIT","unusable rest falls back to visible entry")
range=7; scan.first_step={}; BOT.paused=false
assert(act(scan) and BOT.paused,"do not rest indefinitely against isolated ranged attacker")
BOT.paused=false; BOT.encounter.unseen=true
assert(not act(scan),"unseen threat retains dedicated handling")
BOT.encounter.unseen=false; scan.reachable_any=true
assert(not act(scan) and not BOT.isolated_recovering,"reachable enemy restores combat")
depth=7; observe(scan)
assert(BOT.recovery_anchor.level=="D:7" and not BOT.recovery_anchor.rest,
 "floor changes discard stale relative anchors")
print("isolated recovery regression cases passed")
