-- V6 observation additions using only ordinary player-visible Lua APIs.
-- Never read laboratory-only durations, hidden monsters, or RNG here.
local ga_player_v5 = ga_player
ga_player = function()
  local result = ga_player_v5()
  -- x_pos/y_pos are unavailable in the ordinary player Lua sandbox in this
  -- build. Do not publish fabricated zero coordinates as measured positions.
  result.x = ga_you("x_pos")
  result.y = ga_you("y_pos")
  for _, key in ipairs({"piety_rank", "hasted", "slowed", "exhausted",
      "teleporting", "anchored", "invisible", "mesmerised", "petrifying",
      "silencing", "regenerating", "mighty", "caught"}) do
    local value = ga_you(key)
    if value ~= nil then result[key] = value end
  end
  result.abilities = ga_you("ability_info") or {}
  return result
end
