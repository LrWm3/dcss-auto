local function upvalue(fn,wanted,seen)
  seen=seen or {}; if seen[fn] then return end; seen[fn]=true
  for i=1,100 do
    local name,value=debug.getupvalue(fn,i)
    if not name then break end
    if name==wanted then return value end
    if type(value)=="function" then
      local found=upvalue(value,wanted,seen); if found then return found end
    end
  end
end
local route=assert(upvalue(ready,"route_action"))
local commands={}
local branch,depth,turn="D",11,100
you={branch=function() return branch end,depth=function() return depth end,
  turns=function() return turn end,num_runes=function() return 3 end,
  have_rune=function() return false end}
travel={find_deepest_explored=function() return 1 end}
crawl.mpr=function() end
crawl.process_keys=function(s) commands[#commands+1]=s end
local scan={cells={},blocked={},any=false}
for n=1,11 do ROUTE_STATE.done["D:"..n]="clear" end
route(scan)
assert(ROUTE_STATE.index==2 and commands[1]=="GL1\r\027\027\027",
  "D11 must route to Lair, never D12")
for n=1,5 do ROUTE_STATE.done["Lair:"..n]="clear" end
branch,depth,turn="Lair",5,101; commands={}
route(scan)
assert(ROUTE_STATE.index==3 and commands[1]=="GD12\r\027\027\027")
ROUTE_STATE.done["D:12"]="clear"; commands={}; turn=102
route(scan)
assert(ROUTE_STATE.index==4 and commands[1]=="GO1\r\027\027\027")
ROUTE_STATE.entrances.Shoals="Lair:2"
travel.find_deepest_explored=function(b) return b=="Shoals" and 1 or 0 end
assert(upvalue(ready,"route_resolve")("wet")=="Shoals")
ROUTE_STATE.index=8; ROUTE_STATE.done["Shoals:4"]="clear"; BOT.paused=false
route(scan)
assert(BOT.paused and ROUTE_STATE.index==8,"floor completion is not rune collection")
BOT.paused=false; you.have_rune=function(r) return r=="barnacled" end
ROUTE_STATE.entrances.Snake="Lair:3"; commands={}; turn=103
route(scan)
assert(ROUTE_STATE.index==9 and commands[1]=="GP4\r\027\027\027")
local saved=c_save(); local expected=ROUTE_STATE.index
ROUTE_STATE=nil; assert(load(saved))()
assert(ROUTE_STATE.index==expected and ROUTE_STATE.choices.wet=="Shoals",
  "route progress must survive character save/load")
AUTOCrawl_ROUTE.allow_partial=false
ROUTE_STATE.index=1; ROUTE_STATE.done["D:11"]="partial"
branch,depth,turn="D",11,104; commands={}
route(scan)
assert(ROUTE_STATE.index==1 and commands[1]=="o\027\027\027",
  "strict completion must not accept a partly explored floor")
commands={}
crawl.sendkeys=crawl.process_keys
c_message("Are you sure you want to cancel this blink?")
assert(#commands==0 and c_answer_prompt("Are you sure you want to cancel this blink?")==true)
commands={}
c_message("The barbs in your skin will harm you if you move. Continue?")
assert(commands[1]=="Y")
local excluded=nil
travel.set_exclude=function(x,y,r) excluded={x,y,r} end
upvalue(ready,"route_observe")({cells={
  ["1:2"]={x=1,y=2,feature="runed_clear_door"},
  ["2:2"]={x=2,y=2,feature="enter_lair"}}})
assert(excluded[1]==1 and excluded[2]==2 and excluded[3]==1)
assert(ROUTE_STATE.entrances.Lair=="D:11")
local escape=assert(upvalue(ready,"escape_exclusion"))
view={is_safe_square=function(x,y) return x~=1 end}
local pocket={cells={
  ["0:0"]={x=0,y=0,feature="floor",traversable=true},
  ["1:0"]={x=1,y=0,feature="floor",traversable=true,excluded=true},
  ["2:0"]={x=2,y=0,feature="floor",traversable=true}},blocked={}}
commands={}
assert(escape(pocket) and commands[1]=="l", "escape travel exclusions over safe terrain")
assert(c_answer_prompt("Really walk into a travel-excluded area?")==true,
  "deliberate exclusion escape must answer its confirmation synchronously")
assert(c_answer_prompt("Really walk into a travel-excluded area?")==nil,
  "exclusion permission must be consumed, not approve unrelated movement")
assert(c_answer_prompt("Really walk into a cloud of flame?")==nil,
  "exclusion escape must not approve other hazards")
pocket.cells["1:0"].unsafe=true
commands={}
assert(not escape(pocket) and #commands==0, "exclusion escape must still reject hazards")
print("route regression cases passed")
