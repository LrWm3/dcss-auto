local function find(fn,wanted,seen)
 seen=seen or {}; if seen[fn] then return end; seen[fn]=true
 for i=1,100 do local n,v=debug.getupvalue(fn,i); if not n then break end
  if n==wanted then return v end
  if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
 end
end
local act=assert(find(ready,"sigmund_action"))
local approach=assert(find(ready,"approach_action"))
local hp,used=56,nil
you={hp=function() return hp,56 end,turns=function() return 100 end,
 confused=function() return false end,transform=function() return "" end,
 status=function() return false end,berserk=function() return false end,
 slowed=function() return false end,exhausted=function() return false end,
 ability_info=function() return {{"Berserk",true,"a"}} end,
 activate_ability=function(n) used=n; return true end}
view={is_safe_square=function() return true end,feature_at=function() return "floor" end}
local last; crawl.sendkeys=function(k) last=k end
crawl.do_commands=function(c) last=c[1] end; crawl.mpr=function() end; crawl.take_note=function() end
BOT.encounter={hidden_caster={name="Sigmund"}}
local scan={any=true,reachable_any=true,monsters={{x=2,y=0,monster={name=function() return "Sigmund" end}}},cells={},blocked={}}
AUTOCrawl_TACTICS.sigmund_mode=1
assert(not approach(scan),"Sigmund exception skips lure")
assert(not act(scan),"mode1 leaves other combat unchanged")
AUTOCrawl_TACTICS.sigmund_mode=2
assert(act(scan) and used=="Berserk","rage before closing final reaching gap")
hp=20; used=nil; assert(not act(scan) and not used,"do not early rage below HP floor")
AUTOCrawl_TACTICS.sigmund_mode=3; BOT.encounter.hidden_missing=true
scan.any=false; scan.monsters={}
scan.cells={["0:0"]={x=0,y=0,feature="floor",traversable=true},
 ["-1:0"]={x=-1,y=0,feature="stone_stairs_up_i",traversable=true}}
assert(act(scan) and last=="h","withdraw instead of following disturbance")
BOT.encounter.sigmund_retreats=12
assert(act(scan) and last=="CMD_WAIT","bound retreat path")
BOT.encounter.hidden_caster.name="orc wizard"
assert(not act(scan),"Sigmund only")
print("Sigmund policy regression cases passed")
