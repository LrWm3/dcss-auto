local function find(fn,wanted,seen)
  seen=seen or {}; if seen[fn] then return end; seen[fn]=true
  for i=1,100 do
    local name,value=debug.getupvalue(fn,i)
    if not name then break end
    if name==wanted then return value end
    if type(value)=="function" then
      local result=find(value,wanted,seen); if result then return result end
    end
  end
end
local observe=assert(find(ready,"route_observe"))
local recover=assert(find(ready,"route_recovery_action"))
local depth=11
local hp=100
local keys={}
you={branch=function() return "D" end,depth=function() return depth end,
  hp=function() return hp,100 end,berserk=function() return false end,
  slowed=function() return false end,exhausted=function() return false end,
  confused=function() return false end}
crawl.mpr=function() end
crawl.sendkeys=function(key) keys[#keys+1]=key end
crawl.do_commands=function(cmds) keys[#keys+1]=cmds[1] end
view={feature_at=function() return "floor" end,can_reach=function() return true end,
  is_safe_square=function() return true end}
local function cell(x,feature,frontier)
  return {x=x,y=0,feature=feature or "floor",traversable=true,frontier=frontier}
end
local scan={cells={["0:0"]=cell(0),["1:0"]=cell(1),
  ["2:0"]=cell(2,"stone_stairs_up_i")},blocked={},any=false}
ROUTE_STATE.target={branch="D",depth=11}
observe(scan); depth=14; observe(scan)
assert(ROUTE_STATE.recovery.depth==11 and ROUTE_STATE.index==1)
assert(recover(scan) and keys[#keys]=="l","prefer upstairs path")
hp=50
assert(recover(scan) and keys[#keys]=="CMD_WAIT","heal before further discovery")
hp=100
scan.any=true; scan.reachable_adjacent=true
assert(not recover(scan),"adjacent combat keeps priority")
scan.reachable_adjacent=false
assert(recover(scan),"do not pursue distant hostiles")
scan.any=false
view.feature_at=function() return "stone_stairs_up_i" end
for _,n in ipairs({14,13,12}) do
  depth=n; observe(scan)
  assert(recover(scan) and keys[#keys]=="<")
end
assert(not ROUTE_STATE.done["D:14"] and not ROUTE_STATE.done["D:12"])
local saved=c_save(); ROUTE_STATE=nil; assert(load(saved))()
assert(ROUTE_STATE.recovery.depth==11,"save preserves recovery")
depth=11; observe(scan)
assert(not ROUTE_STATE.recovery and not recover(scan))
-- Planned D14 travel is not an overshoot.
ROUTE_STATE.target.depth=14; depth=14; observe(scan)
assert(not ROUTE_STATE.recovery)
-- Interbranch travel may descend normally; a shaft must instead return.
ROUTE_STATE.target={branch="Lair",depth=1}
depth=10; observe(scan); depth=11; observe(scan)
assert(not ROUTE_STATE.recovery)
c_message("You fall into a shaft and drop 3 floors!")
depth=14; observe(scan)
assert(ROUTE_STATE.recovery.depth==11)
-- Unknown exit: one ordinary step, even when standing on downstairs.
view.feature_at=function() return "stone_stairs_down_i" end
scan.cells={["0:0"]=cell(0,"stone_stairs_down_i",true)}
assert(recover(scan) and keys[#keys]~="<" and keys[#keys]~="o" and keys[#keys]~=">")
scan.cells={["0:0"]=cell(0)}
BOT.paused=false
assert(recover(scan) and BOT.paused,"no exit must not imply descend/clear")
print("route recovery regression cases passed")
