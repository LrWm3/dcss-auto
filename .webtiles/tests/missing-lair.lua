local function find(fn,wanted,seen)
 seen=seen or {}; if seen[fn] then return end; seen[fn]=true
 for i=1,100 do local n,v=debug.getupvalue(fn,i); if not n then break end
  if n==wanted then return v end
  if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
 end
end
local act=assert(find(ready,"missing_lair_action"))
local turn,depth,last=100,11,nil
you={branch=function() return "D" end,depth=function() return depth end,
 turns=function() return turn end,confused=function() return false end,
 transform=function() return "" end,status=function() return false end}
travel={find_deepest_explored=function() return 0 end}
crawl.mpr=function() end; crawl.take_note=function() end
crawl.process_keys=function(k) last=k end
crawl.do_commands=function(c) last=c[1] end
local scan={cells={a={visible=true,cloud="poison"}},any=false}
ROUTE_STATE.done["D:11"]="partial"
assert(act(scan) and last=="CMD_WAIT","temporary clouds are not completion")
scan.cells={}; turn=101
assert(act(scan) and last=="o\027\027\027" and not ROUTE_STATE.done["D:11"])
ROUTE_STATE.done["D:11"]="partial"
assert(act(scan) and last=="GD10\r\027\027\027","revisit another candidate, do not idle")
scan.any=true; assert(not act(scan),"combat takes priority")
scan.any=false; ROUTE_STATE.entrances.Lair="D:11"
assert(not act(scan) and not ROUTE_STATE.entrance_search,"discovery resumes normal route")
ROUTE_STATE.entrances.Lair=nil
ROUTE_STATE.entrance_search={started=100,pass=3}
BOT.paused=false; assert(act(scan) and BOT.paused,"bounded exhaustion")
print("missing Lair regression cases passed")
