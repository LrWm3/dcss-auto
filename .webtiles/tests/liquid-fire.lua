local function find(fn,wanted,seen)
 seen=seen or {}; if seen[fn] then return end; seen[fn]=true
 for i=1,100 do
  local n,v=debug.getupvalue(fn,i); if not n then break end
  if n==wanted then return v end
  if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
 end
end
local act=assert(find(ready,"liquid_fire_action"))
local burning=true
you={status=function(s) return burning and s=="liquid fire" end,
 hp=function() return 50,100 end,transform=function() return "" end,
 confused=function() return false end}
view={}; local last
crawl.sendkeys=function(k) last=k end; crawl.take_note=function() end
local scan={cells={["-1:0"]={visible=true,traversable=true,feature="floor"}},blocked={},monsters={{x=2,y=0}}}
assert(act(scan) and last=="h","burning must move even without a hostile in melee")
scan.cells["-1:0"].monster={}; assert(not act(scan),"never bump an occupant")
scan.cells["-1:0"].monster=nil; scan.cells["-1:0"].unsafe=true
assert(not act(scan),"do not enter hazardous terrain")
scan.cells["-1:0"].unsafe=false; burning=false
assert(not act(scan),"ordinary rest remains unchanged")
print("liquid fire regression cases passed")
