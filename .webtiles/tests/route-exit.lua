local function find(fn,wanted,seen)
 seen=seen or {}; if seen[fn] then return end; seen[fn]=true
 for i=1,100 do local n,v=debug.getupvalue(fn,i); if not n then break end
  if n==wanted then return v end
  if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
 end
end
local action=assert(find(ready,"route_exit_action"))
local branch,feature,last="Lair","floor",nil
you={branch=function() return branch end,confused=function() return false end,
 transform=function() return "" end,status=function() return false end}
view={feature_at=function() return feature end}
crawl.sendkeys=function(k) last=k end
ROUTE_STATE.return_exit="Lair"; ROUTE_STATE.target={branch="D",depth=12}
local scan={any=false,blocked={},cells={
 ["0:0"]={x=0,y=0,traversable=true,feature="floor"},
 ["1:0"]={x=1,y=0,traversable=true,feature="exit_lair"}}}
assert(action(scan) and last=="l")
assert(ROUTE_STATE.target.depth==12,"local exit must not change progression target")
feature="exit_lair";assert(action(scan) and last=="<")
assert(c_answer_prompt("Enter next level anyway?")==nil,"unrelated warnings not approved")
c_message("This staircase leads to a travel-excluded area!")
assert(c_answer_prompt("Enter next level anyway?")==true,"deliberate branch exit confirmation")
assert(c_answer_prompt("Enter next level anyway?")==nil,"permission is single-use")
scan.any=true;last=nil;assert(not action(scan) and not last,"combat retains priority")
branch="D";assert(not action(scan) and not ROUTE_STATE.return_exit)
print("branch return regression cases passed")
