"""Compare default policy traces with a Git checkpoint; requires lupa and git.

uv run --with lupa python .webtiles/tests/compare_policy.py c08ed68
This complements, not replaces, live fixed-seed trials.
"""
import itertools
import subprocess
import sys
from pathlib import Path
from lupa import LuaRuntime

root = Path(__file__).resolve().parents[2]
rc_path = '.webtiles/rcs/codex-autocrawl.rc'
baseline = subprocess.check_output(['git', 'show', f'{sys.argv[1]}:{rc_path}'], cwd=root, text=True)
current = (root / rc_path).read_text()

def body(text):
    return text.split('\n<\n', 1)[1].rsplit('\n>', 1)[0]

HARNESS = r'''
local function find(fn, wanted, seen)
  seen=seen or {}; if seen[fn] then return end; seen[fn]=true
  for i=1,100 do
    local name,value=debug.getupvalue(fn,i); if not name then break end
    if name==wanted then return value end
    if type(value)=="function" then
      local found=find(value,wanted,seen); if found then return found end
    end
  end
end
local survival,encounter=find(ready,"survival_action"),find(ready,"encounter_action")
function trace(hp,count,threat,status,stock,failed)
  local commands,turn={},100
  local inventory={}
  local function emit(cmd)
    commands[#commands+1]=cmd
    if not failed then turn=turn+1 end
  end
  crawl.mpr=function() end
  crawl.process_keys=emit; crawl.sendkeys=emit
  crawl.do_commands=function(cs) emit(table.concat(cs,",")) end
  you={hp=function() return hp,100 end, turns=function() return turn end,
    turn_is_over=function() return turn>100 end,
    berserk=function() return status=="berserk" end,
    confused=function() return status=="confused" end,
    silenced=function() return status=="silenced" end,
    exhausted=function() return status=="exhausted" end,
    slowed=function() return status=="slowed" end,
    poisoned=function() return status=="poisoned" end,
    poison_survival=function() return hp-30 end,
    status=function(s) return s==status end,
    ability_info=function(name) return stock==2 and {{name,true,"a"}} or {} end,
    activate_ability=function(name) emit(name); return not failed end}
  items={inventory=function() return inventory end,
    index_to_letter=function(i) return string.char(97+i) end}
  if stock==1 then
    for i,pair in ipairs({{"potion","curing"},{"potion","heal wounds"},
        {"scroll","teleportation"},{"scroll","fear"},{"potion","haste"},{"potion","might"}}) do
      local kind,name=pair[1],pair[2]
      inventory[#inventory+1]={slot=i,is_identified=true,
        class=function() return kind end,name=function() return kind.." of "..name end}
    end
  end
  local monsters={}
  for i=1,count do monsters[i]={x=1,y=0,reachable=true,threat=threat} end
  local scan={any=count>0,worst=threat,reachable_worst=threat,
    reachable_any=count>0,reachable_adjacent=count>0,
    yellow_adjacent=count>0 and threat==2,monsters=monsters}
  if not survival(scan) then encounter(scan) end
  return table.concat(commands,"|"),turn
end
'''

def run(source, case):
    lua = LuaRuntime()
    lua.execute('crawl={more_autoclear=function() end}; add_autopickup_func=function() end')
    lua.execute(body(source))
    lua.execute(HARNESS)
    return lua.globals().trace(*case)

cases = itertools.product([30,44,45,54,55,69,70,79,80,100], [0,1,3], [1,2,3],
                          ['', 'berserk', 'confused', 'silenced', 'exhausted',
                           'slowed', 'poisoned', 'about to teleport', 'regenerating'],
                          [0,1,2], [False,True])
total=0
for case in cases:
    old,new=run(baseline,case),run(current,case)
    assert old==new, (case,old,new)
    total+=1
print(f'{total} matching policy traces against {sys.argv[1]}')
