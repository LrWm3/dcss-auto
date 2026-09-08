local function find(fn,wanted,seen)
 seen=seen or {}; if seen[fn] then return end; seen[fn]=true
 for i=1,100 do local n,v=debug.getupvalue(fn,i); if not n then break end
  if n==wanted then return v end
  if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
 end
end
local action=assert(find(ready,"shopping_action"))
local priority=assert(find(ready,"shop_priority"))
local turn,gold,last=100,200,nil
you={turns=function() return turn end,gold=function() return gold end,
 branch=function() return "D" end,depth=function() return 4 end,feel_safe=function() return true end}
items={inventory=function() return {} end,equipped_at=function() end}
travel={waypoint_delta=function() return 3,0 end}
crawl.process_keys=function(k) last=k end; crawl.mpr=function() end; crawl.sendkeys=function() end
local d={kind="teleportation",quantity=1,price=33,index=1,name="a scroll of teleportation"}
assert(priority(d)); assert(not priority({kind="identify",quantity=1,price=22}))
ROUTE_STATE.shopping={shops={[0]={offers={d}}},checked={},next_slot=1}
ROUTE_STATE.done["D:4"]="clear"
local scan={any=false}
assert(action(scan) and last=="G0\027\027\027")
local route=assert(find(ready,"route_action"))
assert(not route(scan),"route progression cannot compete with active shopping")
scan.any=true; assert(not action(scan) and ROUTE_STATE.shopping.active,"combat interrupts without travel")
scan.any=false; action(scan); assert(not action(scan) and not ROUTE_STATE.shopping.active,"bounded no-progress abort")
assert(not action(scan),"same departure must not restart aborted shopping")
ROUTE_STATE.shopping.checked={}; action(scan)
BOT.encounter={phase="disengage"}
assert(not action(scan) and not ROUTE_STATE.shopping.active)
BOT.encounter=nil; ROUTE_STATE.shopping.checked={}; action(scan)
c_message("Sorry, I don't know how to get there.")
assert(not ROUTE_STATE.shopping.active,"no-route message aborts immediately")
local catalogue=assert(find(ready,"shop_catalogue"))
local function scroll(name)
 return {is_identified=true,quantity=1,class=function() return "scroll" end,name=function() return name end}
end
items.shop_inventory=function() return {{scroll("scroll of teleportation"),33},{scroll("scroll of noise"),11},{scroll("scroll of identify"),22}} end
travel.waypoint_delta=function() return 0,0 end
catalogue()
assert(ROUTE_STATE.shopping.shops[0].offers[1].index==3,"price-order rank, not raw API index")
items.shop_inventory=function() return {{scroll("scroll of teleportation"),33},{scroll("scroll of fear"),33}} end
catalogue(); assert(#ROUTE_STATE.shopping.shops[0].offers==0,"ambiguous equal-price entries skipped")
ROUTE_STATE.shopping.checked={}; ROUTE_STATE.shopping.shops[0].offers={d}
travel.waypoint_delta=function() return 3,0 end
action(scan); turn=401
assert(not action(scan) and not ROUTE_STATE.shopping.active,"total travel budget bounds moving loops")
-- Purchase menus have queued cancellation input; abort rejected purchases.
turn=500; last=nil; ROUTE_STATE.shopping.checked={}
ROUTE_STATE.shopping.shops[0].offers={d}
travel.waypoint_delta=function() return 0,0 end
view={feature_at=function() return "enter_shop" end}
items.shop_inventory=function() return {{scroll("scroll of teleportation"),33}} end
crawl.do_commands=function(cs) last=cs[1] end
assert(action(scan) and not ROUTE_STATE.shopping.active,
 "purchase rejection must abandon shopping")
ROUTE_STATE.shopping.checked={};ROUTE_STATE.shopping.shops[0].offers={d};last=nil
items.shop_inventory=function() return {} end
assert(action(scan) and last=="CMD_WAIT" and ROUTE_STATE.shopping.active.failed[0],
 "stale offer must yield instead of silently returning to blocking input")
print("shopping regression cases passed")
