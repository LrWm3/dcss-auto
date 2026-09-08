local function find(fn,wanted,seen)
 seen=seen or {}; if seen[fn] then return end; seen[fn]=true
 for i=1,100 do local n,v=debug.getupvalue(fn,i); if not n then break end
  if n==wanted then return v end
  if type(v)=="function" then local r=find(v,wanted,seen); if r then return r end end
 end
end
local act=assert(find(ready,"abyss_action"))
local branch,last="Abyss",nil
you={branch=function() return branch end,depth=function() return 2 end,
 hp=function() return 100,100 end,turns=function() return 100 end,
 confused=function() return false end,berserk=function() return false end,
 poisoned=function() return false end,status=function() return false end,transform=function() return "" end}
you.silenced=function() return false end
items={inventory=function() return {} end}
crawl.take_note=function() end; crawl.mpr=function() end
crawl.sendkeys=function(k) last=k end
crawl.do_commands=function(c) assert(#c==1); last=c[1] end
view={is_safe_square=function() return true end}
local function cell(x,y,f) return {x=x,y=y,feature=f or "floor",traversable=true} end
local scan={cells={["0:0"]=cell(0,0,"exit_abyss")},monsters={},blocked={},first_step={}}
assert(act(scan) and last==">")
scan.cells["0:0"].feature="abyssal_stair"
assert(act(scan) and last=="CMD_WAIT","never descend deeper")
scan.cells["1:0"]=cell(1,0,"exit_abyss")
assert(act(scan) and last=="l","approach actual exit")
scan.cells["1:0"].feature="stone_arch"
scan.cells["-1:0"]=cell(-1,0)
scan.any=true; scan.monsters={{x=2,y=0}}; BOT.abyss.last_resource=100
assert(act(scan) and last=="h","move away from enemy rather than attack")
scan.cells={["0:0"]=cell(0,0)}; scan.monsters={{x=1,y=0}}
assert(act(scan) and last=="CMD_ATTACK_RIGHT","only adjacent blocker when boxed in")
branch="Orc"; assert(not act(scan) and not BOT.abyss,"normal controller resumes after exit")
print("abyss escape regression cases passed")
