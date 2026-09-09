-- Lab-only extension, inside the original RC lexical scope. No map revelation.
local goal_floor
function goal_observation(state)
  observe_encounter(scan_hostiles())
  if goal_floor~=level_key() then
    travel.set_waypoint(8,0,0); goal_floor=level_key()
  end
  local px,py=travel.waypoint_delta(8)
  state.goal_version=1; state.position={x=px,y=py}
  state.known={}; state.anchors={}
  for _,c in pairs(view.get_map()) do
    state.known[map_key(c.x,c.y)]={x=c.x,y=c.y,feature=c.feature,
      visible=c.visible,traversable=c.traversable,frontier=c.frontier,
      mapped=c.mapped,excluded=c.excluded,unsafe=c.unsafe,cloud=c.cloud,
      invisible_monster=c.invisible_monster,occupied=c.visible and c.monster~=nil}
  end
  local a=BOT.recovery_anchor
  local dx,dy=travel.waypoint_delta(9)
  if a and a.level==level_key() and dx and dy then
    for _,kind in ipairs({"stairs","rest","entry"}) do
      local p=a[kind]
      if p then state.anchors[kind]={x=p.x-dx,y=p.y-dy} end
    end
  end
  state.unseen=not not (BOT.encounter and BOT.encounter.unseen)
  state.can_berserk=false
  for _,a in ipairs(you.ability_info("Berserk") or {}) do
    if a[2] then state.can_berserk=true end
  end
end

-- Emergency resources and hazard handling, without explore, chase or rage.
function goal_safety()
  local scan=scan_hostiles()
  observe_encounter(scan); observe_wand_encounter(scan)
  if BOT.ally_attack_rejected then
    BOT.ally_attack_rejected=false; crawl.do_commands({"CMD_WAIT"}); return
  end
  if liquid_fire_action(scan) or survival_action(scan) then return end
  if you.confused() then confused_combat_action(scan); return end
  if not movement_locked() and unsafe_square_action(scan) then return end
  if combat_wand_action(scan) then return end
  if scan.reachable_adjacent then crawl.do_commands({"CMD_AUTOFIGHT_NOMOVE"}); return end
  for _,c in pairs(scan.cells) do
    if c.invisible_monster and math.max(math.abs(c.x),math.abs(c.y))==1
        and not c.monster then
      local cmd=CONFUSED_MOVE_COMMANDS[map_key(c.x,c.y)]
      if cmd then crawl.do_commands({(cmd:gsub("CMD_MOVE_","CMD_ATTACK_"))}); return end
    end
  end
  crawl.do_commands({"CMD_WAIT"})
end
tb_direct_actions[#tb_direct_actions+1]="goal_safety"
tb_direct_actions[#tb_direct_actions+1]="CMD_GO_UPSTAIRS"
