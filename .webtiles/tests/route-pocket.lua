local function find(fn,wanted,seen)
 seen=seen or {}; if seen[fn] then return end; seen[fn]=true
 for i=1,100 do local n,v=debug.getupvalue(fn,i); if not n then break end
  if n==wanted then return v end
  if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
 end
end
local act=assert(find(ready,"route_pocket_action"))
local depth,last=2,nil
you={branch=function() return "Shoals" end,depth=function() return depth end,
 confused=function() return false end,transform=function() return "" end,status=function() return false end}
view={is_safe_square=function() return true end}
crawl.sendkeys=function(k) last=k end; crawl.process_keys=crawl.sendkeys; crawl.mpr=function() end
local function cell(x,f) return {x=x,y=0,feature=f,traversable=true} end
local scan={cells={["0:0"]=cell(0,"stone_stairs_up_i")},blocked={}}
ROUTE_STATE.pocket={branch="Shoals",depth=2,tried={}}
ROUTE_STATE.done["Shoals:2"]="clear"
assert(act(scan) and last=="<")
depth=1; scan.cells={["0:0"]=cell(0,"stone_stairs_down_i"),["1:0"]=cell(1,"stone_stairs_down_ii")}
assert(act(scan) and last=="l" and ROUTE_STATE.pocket.tried.stone_stairs_down_i)
scan.cells={["0:0"]=cell(0,"stone_stairs_down_ii")}
assert(act(scan) and last==">")
depth=2; scan.cells={["0:0"]=cell(0,"stone_stairs_up_ii")}
assert(act(scan) and last=="o\027\027\027" and not ROUTE_STATE.done["Shoals:2"])
scan.cells["1:0"]=cell(1,"stone_stairs_down_i")
assert(act(scan) and not ROUTE_STATE.pocket)
ROUTE_STATE.pocket={branch="Shoals",depth=2,tried={stone_stairs_down_i=true,stone_stairs_down_ii=true,stone_stairs_down_iii=true}}
depth=1; scan.cells={["0:0"]=cell(0,"stone_stairs_down_i")}
scan.any=true; assert(not act(scan),"combat wins")
scan.any=false; BOT.paused=false
assert(act(scan) and BOT.paused,"exhausted stairs pause instead of looping")
local route=assert(find(ready,"route_action"))
you.turns=function() return 100 end; you.num_runes=function() return 0 end
travel={find_deepest_explored=function() return 2 end}
depth=2; BOT.paused=false; ROUTE_STATE.pocket=nil
ROUTE_STATE.index=6; ROUTE_STATE.choices.wet="Shoals"
ROUTE_STATE.done["Shoals:1"]="partial"; ROUTE_STATE.done["Shoals:2"]="clear"
scan.cells={["0:0"]=cell(0,"stone_stairs_up_i")}
for i=1,4 do route(scan) end
assert(ROUTE_STATE.pocket and last=="<","allowed partial parent supports recovery")
print("route pocket regression cases passed")
