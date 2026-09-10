-- Synthetic waves, inserted before tactical_dump scans visible entities.
-- Lab-only metadata is for auditing, not an input to a learned policy.
local chain_stage = 0
local chain_boundary
local chain_failed = false
function chain_tick()
  assert(not chain_failed, "Previous wave transition failed; abort this trial")
  local before = you.tactical_wave("status")
  chain_boundary = nil
  if chain_stage == 0 then
    you.tactical_wave("reset")
  end
  if before.alive == 0 and chain_stage < #CHAIN_WAVES then
    chain_failed = true
    chain_stage = chain_stage + 1
    local after = you.tactical_wave("spawn", CHAIN_WAVES[chain_stage],
      CHAIN_SETUP_SEED + chain_stage)
    for _,k in ipairs({"turn","hp","max_hp","mp","max_mp","x","y"}) do
      assert(before[k] == after[k], "Wave changed player "..k)
    end
    for _,k in ipairs({"elapsed_time","berserk_penalty"}) do
      assert(before[k] == after[k], "Wave changed player "..k)
    end
    for k,v in pairs(before.durations) do
      assert(after.durations[k] == v, "Wave changed player duration")
    end
    chain_boundary = {before=before, after=after, stage=chain_stage}
    chain_failed = false
  end
end
local chain_parent_observation = goal_observation
function goal_observation(state)
  chain_parent_observation(state)
  state.chain = {stage=chain_stage, total=#CHAIN_WAVES,
    native=you.tactical_wave("status"), boundary=chain_boundary}
end
