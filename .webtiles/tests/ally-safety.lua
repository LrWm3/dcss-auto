local function find(fn,wanted,seen)
 seen=seen or {}; if seen[fn] then return end; seen[fn]=true
 for i=1,100 do local n,v=debug.getupvalue(fn,i); if not n then break end
  if n==wanted then return v end
  if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
 end
end
local probe=assert(find(ready,"safe_probe_command"))
local step=assert(find(ready,"can_step"))
local scan={cells={}}
BOT.disturbance_turns=0
local ally={attitude=function() return 4 end}
scan.cells["-1:-1"]={monster=ally}
assert(probe(scan)=="CMD_ATTACK_UP","skip friendly in default blind direction")
assert(probe(scan,"CMD_ATTACK_UP_LEFT")=="CMD_ATTACK_UP","reject preferred friendly disturbance")
for x=-1,1 do for y=-1,1 do
 if x~=0 or y~=0 then scan.cells[x..":"..y]={monster=ally} end
end end
assert(probe(scan)=="CMD_WAIT","all adjacent cells protected: consume wait, not prompt")
scan.cells["0:-1"].monster={attitude=function() return 0 end}
assert(probe(scan)=="CMD_ATTACK_UP","hostile remains valid")
view={is_safe_square=function() return true end}
you={confused=function() return false end}
local cells={["1:0"]={x=1,y=0,traversable=true,feature="floor",monster=ally}}
assert(not step(cells,0,0,1,0,{}),"custom movement cannot attack protected occupant")
cells["1:0"].monster=nil; assert(step(cells,0,0,1,0,{}))
local key
crawl.sendkeys=function(k) key=k end
c_message("Really attack your two-headed ogre?","prompt")
assert(key=="n" and BOT.ally_attack_rejected,"confirmation fails closed and schedules a real turn")
print("ally safety regression cases passed")
