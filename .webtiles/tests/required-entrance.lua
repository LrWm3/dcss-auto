local function find(fn,wanted,seen)
 seen=seen or {}; if seen[fn] then return end; seen[fn]=true
 for i=1,100 do local n,v=debug.getupvalue(fn,i); if not n then break end
  if n==wanted then return v end
  if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
 end
end
local act=assert(find(ready,"required_entrance_action"))
you={branch=function() return "D" end,confused=function() return false end,
 transform=function() return "" end,status=function() return false end}
view={is_safe_square=function() return false end}
local last; crawl.sendkeys=function(k) last=k end; crawl.mpr=function() end
ROUTE_STATE.target={branch="Lair",depth=1}; ROUTE_STATE.required_entrance=true
local scan={cells={},blocked={}}
for x=0,2 do scan.cells[x..":0"]={x=x,y=0,feature=x==2 and "enter_lair" or "floor",traversable=true,excluded=true} end
assert(act(scan) and last=="l" and BOT.allow_exclusion_step)
assert(scan.cells["1:0"].excluded,"shared exclusion map unchanged")
scan.cells["1:0"].cloud="steam"; scan.cells["1:0"].unsafe=true
assert(not act(scan),"no cloud override")
scan.cells["1:0"].cloud=nil; scan.cells["1:0"].unsafe=nil
scan.cells["1:0"].monster={attitude=function() return 4 end}
assert(not act(scan),"no friendly bump")
scan.cells["1:0"].monster=nil; scan.reachable_adjacent=true
assert(not act(scan),"adjacent combat keeps priority")
scan.reachable_adjacent=false; scan.cells={["0:0"]={x=0,y=0,feature="enter_lair"}}
assert(act(scan) and last==">")
you.branch=function() return "Lair" end
assert(not act(scan) and not ROUTE_STATE.required_entrance)
print("required entrance regression cases passed")
