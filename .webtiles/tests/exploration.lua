-- Run after loading the rc Lua block. Exercise the actual local controller.
local explore
for i = 1, 100 do
  local name, value = debug.getupvalue(ready, i)
  if not name then break end
  if name == "explore_frontier" then explore = value end
end
assert(explore)
local commands = {}
crawl.sendkeys = function(s) commands[#commands+1] = s end
crawl.process_keys = crawl.sendkeys
crawl.do_commands = function(cs)
  for _, s in ipairs(cs) do commands[#commands+1] = s end
end
crawl.mpr = function() end
you = {branch=function() return "D" end, depth=function() return 7 end}
view = {feature_at=function() return "stone_stairs_down" end,
        can_reach=function() return false end}
local scan = {any=false, blocked={}, cells={
  ["0:0"]={x=0,y=0,traversable=true,feature="stone_stairs_down"},
  ["1:0"]={x=1,y=0,traversable=true,feature="floor",frontier=true}}}
explore(scan, true)
assert(commands[1] == "o\027\027\027", "native explore must include modal-menu guards even on stairs")
commands = {}
scan.any = true
explore(scan, false)
assert(commands[1] == "l", "custom exploration must walk toward frontier, not descend")
commands = {}
scan.cells["1:0"].frontier = false
BOT.paused = false
explore(scan, false)
assert(#commands == 0 and BOT.paused, "no frontier must not cause descent")
BOT.paused = false
c_message("Partly explored, can't reach some items.", "plain")
assert(BOT.floor_partial["D:7"] and not BOT.floor_done["D:7"])
BOT.paused = false
c_message("<lightgrey>Done exploring.", "plain")
assert(BOT.floor_done["D:7"], "only completed exploration authorizes stair survey")
commands={}
scan.any=false
scan.cells["1:0"].frontier=true
BOT.custom_exploring_level="D:7"
explore(scan,true)
assert(commands[1]=="l", "losing sight of an isolated enemy must not restart greedy native explore")
commands={}
scan.cells["0:0"].frontier=true
view.can_reach=function() return true end
explore(scan,false)
assert(commands[1]=="h", "reveal unknown neighbor before walking to another frontier")
commands={}
scan.cells["0:0"].frontier=false
scan.cells["1:0"].frontier=false
explore(scan,true)
assert(commands[1]=="o\027\027\027" and not BOT.custom_exploring_level,
  "return to native loot exploration when custom frontiers are exhausted")
c_message("Partly explored, unvisited transporter.","plain")
assert(ROUTE_STATE.done["D:7"]=="partial" and not BOT.floor_done["D:7"],
  "optional transporter is a partial floor, not an upstairs retreat or a full clear")
commands={}
assert(c_answer_prompt("Really explore while Zot is near?")==true,
  "Zot warning must use the synchronous prompt hook")
assert(c_answer_prompt("An unrelated confirmation?")==nil and #commands==0,
  "do not accept unrelated prompts or leak answer keys into gameplay")
print("exploration regression cases passed")
