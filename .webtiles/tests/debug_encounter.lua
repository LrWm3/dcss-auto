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
local real_report=autocrawl_debug_report
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
-- The API takes spell names, not item names: Charm, not Charming.
local calls={}
local monster={name=function() return "ogre" end,attitude=function() return 0 end,
  is_firewood=function() return false end,threat=function() return 2 end,
  defeat_wl=function(self,spell,evoked)
    assert(evoked and (spell=="Charm" or spell=="Mindburst"))
    calls[spell]=true; return spell=="Charm" and 62 or 81
  end}
view={get_map=function() return {{x=1,y=0,visible=true,monster=monster}} end,
  can_reach=function() return true end}
you={hp=function() return 91,91 end,turns=function() return 8128 end,
  branch=function() return "D" end,depth=function() return 10 end,
  berserk=function() return false end,slowed=function() return false end,
  exhausted=function() return false end}
items={inventory=function() return {} end}
local report=real_report()
assert(calls.Charm and calls.Mindburst and report[3]:find("charm=62",1,true))
print("debug encounter regression cases passed")
