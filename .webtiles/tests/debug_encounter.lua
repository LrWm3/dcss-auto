local function find(fn,wanted,seen)
  seen=seen or {}; if seen[fn] then return end; seen[fn]=true
  for i=1,100 do
    local name,value=debug.getupvalue(fn,i)
    if not name then break end
    if name==wanted then return value end
    if type(value)=="function" then
      local result=find(value,wanted,seen); if result then return result end
    end
  end
end
local pause=assert(find(ready,"debug_encounter_pause"))
local reported=0
autocrawl_debug_report=function() reported=reported+1 end
crawl.mpr=function() end
local scan={monsters={{monster={name=function() return "Lodul" end}}}}
assert(not pause(scan) and not BOT.paused,"breakpoints default off")
AUTOCrawl_TACTICS.debug_encounters=true
assert(pause(scan) and BOT.paused and reported==1)
local saved=c_save(); AUTOCrawl_DEBUG_STATE=nil; assert(load(saved))()
assert(AUTOCrawl_DEBUG_STATE.paused and AUTOCrawl_DEBUG_STATE.seen.lodul)
autocrawl_debug_resume()
assert(not BOT.paused and not AUTOCrawl_DEBUG_STATE.paused and not pause(scan))
print("debug encounter regression cases passed")
