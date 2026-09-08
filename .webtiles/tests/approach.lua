local function find(fn,wanted,seen)
 seen=seen or {}; if seen[fn] then return end; seen[fn]=true
 for i=1,100 do local n,v=debug.getupvalue(fn,i); if not n then break end
  if n==wanted then return v end
  if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
 end
end
local act=assert(find(ready,"approach_action"))
local hp,range,name=71,1,"orc"
you={hp=function() return hp,71 end,berserk=function() return false end,
 confused=function() return false end,status=function() return false end,
 transform=function() return "" end,branch=function() return "D" end,depth=function() return 6 end}
view={is_safe_square=function() return true end}
local last
crawl.mpr=function() end; crawl.take_note=function() end
crawl.sendkeys=function(k) last=k end; crawl.do_commands=function(c) last=c[1] end
local scan={any=true,reachable_any=true,monsters={{x=0,y=-5,reachable=true,
 monster={name=function() return name end,range=function() return range end}}},
 cells={["0:1"]={x=0,y=1,feature="floor",visible=true,traversable=true}},blocked={},first_step={}}
AUTOCrawl_TACTICS.approach_mode=1; BOT.encounter={}
for i=1,4 do assert(act(scan) and last=="CMD_WAIT") end
assert(not act(scan),"bounded wait")
BOT.encounter={}; assert(act(scan)); hp=70
assert(not act(scan),"damage immediately cancels waiting")
hp=71; range=7; BOT.encounter={}; assert(not act(scan),"do not wait against ranged")
range=1; name="steam dragon"; BOT.encounter={}; assert(not act(scan),"steam exception")
name="orc"; scan.reachable_adjacent=true; BOT.encounter={}; assert(not act(scan))
scan.reachable_adjacent=false; assert(not act(scan),"do not restart lure after melee begins")
BOT.encounter={}; AUTOCrawl_TACTICS.approach_mode=2
BOT.recovery_anchor={level="D:6",entry={x=0,y=0}}
travel={waypoint_delta=function() return 0,-5 end}
assert(act(scan) and last=="j","lure toward entry and away from enemy")
scan.cells["0:1"].frontier=true; BOT.encounter={}
assert(act(scan) and last=="CMD_WAIT","never lure onto frontier")
AUTOCrawl_TACTICS.approach_mode=3; BOT.encounter={}
assert(not act(scan),"mode3 permits nonfrontier approach")
scan.first_step["1:-5"]="j"
assert(act(scan) and last=="CMD_WAIT","mode3 holds when path begins on frontier")
print("approach regression cases passed")
