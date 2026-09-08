-- Run after loading the rc's Lua block in a mocked Crawl environment.
local state, commands, messages
local function setup(form, status, confused, threat, adjacent)
  state = {turn = 1, form = form or "", status = status, confused = confused}
  commands, messages = {}, {}
  BOT.paused = false
  BOT.encounter = nil
  BOT.move_rejected_at = nil
  BOT.move_rejected_reason = nil
  BOT.directional_rejected_at = nil
  BOT.move_rejected_announced = false
  BOT.immobile_announced = false
  BOT.red_announced = false
  you = {
    branch = function() return "D" end,
    depth = function() return 2 end,
    hp = function() return 100,100 end,
    species = function() return "Minotaur" end,
    class = function() return "Berserker" end,
    transform = function() return state.form end,
    status = function(s) return s == state.status end,
    turns = function() return state.turn end,
    confused = function() return state.confused end,
    mesmerised = function() return state.mesmerised end,
    berserk = function() return false end,
    exhausted = function() return false end,
    slowed = function() return false end,
    activate_ability = function() return false end,
  }
  crawl.mpr = function(s)
    if not s:find("encounter:",1,true) then messages[#messages+1] = s end
  end
  crawl.sendkeys = function(s) commands[#commands+1] = s end
  crawl.do_commands = function(cs)
    assert(#cs == 1, "multiple commands bypass per-turn checks")
    commands[#commands+1] = cs[1]
  end
  view = {
    feature_at = function() return "floor" end,
    can_reach = function() return true end,
    get_map = function()
      local cells = {{x=0,y=0,traversable=true,feature="floor"}}
      if threat then
        cells[#cells+1] = {x=adjacent and 1 or 2,y=0,visible=true,
          traversable=true,feature="floor", monster={
            attitude=function() return 0 end,
            is_firewood=function() return false end,
            threat=function() return threat end}}
      end
      return cells
    end,
  }
end

for _, restriction in ipairs({"tree", "immotile", "fortress blast charging"}) do
  setup(restriction == "tree" and "tree" or "", restriction)
  ready()
  assert(commands[1] == "CMD_WAIT")
  setup(restriction == "tree" and "tree" or "", restriction, false, 1, true)
  ready()
  assert(commands[1] == "\t", "adjacent grey must be attacked")
  setup(restriction == "tree" and "tree" or "", restriction, false, 1, false)
  for i=1,20 do ready() end
  assert(#commands == 0 and #messages == 1, "distant threat must not cause blind waiting")
end
setup("tree", nil, true, 1, true)
ready()
assert(#commands == 0, "confused tree must not attempt movement")
setup("tree", nil, false, 3, true)
ready()
assert(commands[1] == "\t", "adjacent red now uses normal combat even in tree form")
setup()
c_message("You cannot move.", "plain")
for i=1,50 do ready() end
assert(#commands == 0 and #messages == 1, "unknown rejection must not loop")
state.turn = 2
state.form = "tree"
ready()
assert(commands[1] == "CMD_WAIT" and BOT.move_rejected_at == nil)
print("movement-lock regression cases passed")

-- Mesmerisation limits directions, not all movement or melee.
setup("", nil, false, 1, false)
state.mesmerised = true
local original_map = view.get_map
view.get_map = function()
  local cells = original_map()
  for _, p in ipairs({{1,0},{0,1},{1,1},{2,1}}) do
    cells[#cells+1] = {x=p[1],y=p[2],visible=true,traversable=true,feature="floor"}
  end
  return cells
end
view.withheld = function(x,y) return x==1 and y==0 end
ready()
assert(commands[1] and commands[1]~="l" and commands[1]~="\t"
    and commands[1]~="CMD_WAIT", "must find a legal alternative first step")
commands = {}
view.withheld = function() return true end
ready()
assert(commands[1]=="CMD_WAIT", "conflicting beholders must not strand ready")
commands = {}
BOT.move_rejected_at = state.turn -- pre-fix hotload latch, no reason recorded
ready()
assert(commands[1]=="CMD_WAIT" and not BOT.move_rejected_at,
    "old mesmerisation latch must recover without manual gameplay")
commands = {}
state.turn = state.turn+1
view.withheld = function() return false end
ready()
assert(commands[1] and commands[1]~="CMD_WAIT", "retry only after time advances")
commands = {}
c_message("You cannot move away from the merfolk siren!", "plain")
ready()
assert(commands[1]=="CMD_WAIT" and not BOT.move_rejected_at)
commands = {}
state.turn = state.turn+1
c_message("You cannot move.", "plain")
ready()
assert(#commands==0, "unknown rejection must still pause even when mesmerised")

setup("", nil, false, 1, true)
state.mesmerised = true
view.withheld = function() return true end
ready()
assert(commands[1]=="CMD_ATTACK_RIGHT", "adjacent attack must not pursue")
setup("", nil, true, 1, true)
state.mesmerised = true
view.withheld = function() return true end
ready()
assert(commands[1]=="CMD_MOVE_RIGHT", "confusion retains engine stumble handling")
setup("tree", nil, true, 1, true)
state.mesmerised = true
ready()
assert(#commands==0, "mesmerisation must not bypass genuine immobility")
setup("", nil, false, 1, true)
state.mesmerised = false
ready()
assert(commands[1]=="\t", "ordinary combat resumes after mesmerisation")
print("mesmerisation regression cases passed")
