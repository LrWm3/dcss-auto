-- Read the controller's action inside ready(), without another input cycle.
-- Even a Lua command macro introduces a macro delay and extra _prep_input calls.
TB_DIRECT_TRANSPORT=true
TB_DIRECT_SAVE=true
local tb_direct_ready=ready
local tb_direct_actions={"baseline","CMD_WAIT","CMD_AUTOFIGHT","CMD_AUTOFIGHT_NOMOVE",
  "berserk","CMD_MOVE_UP","CMD_MOVE_DOWN","CMD_MOVE_LEFT","CMD_MOVE_RIGHT",
  "CMD_MOVE_UP_LEFT","CMD_MOVE_UP_RIGHT","CMD_MOVE_DOWN_LEFT","CMD_MOVE_DOWN_RIGHT"}
function ready()
  tb_direct_ready()
  if TB.active and not you.turn_is_over() and not TB.pending then
    crawl.redraw_screen()
    local key=crawl.getch()
    if key==27 then return end -- explicit administrative console escape
    if key==122 then -- z: checkpoint without an extra interpreter/input cycle
      TB.reported=nil -- the loaded worker must publish its initial observation
      crawl.do_commands({"CMD_SAVE_GAME_NOW"}); return
    end
    local action=tb_direct_actions[key-96]
    if action then tb_request(action);tb_direct_ready() end
  end
end
