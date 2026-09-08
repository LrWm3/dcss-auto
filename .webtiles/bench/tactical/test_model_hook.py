"""uv run --with lupa python .webtiles/bench/tactical/test_model_hook.py"""
from pathlib import Path
from lupa import LuaRuntime

hook=(Path(__file__).parent/'model_hook.lua').read_text()


def vm():
    lua=LuaRuntime()
    lua.execute('''
      tick=100; floor="D:4"; count=1; distance=6; hp=100; calls=0
      BOT={}; AUTOCrawl_DEBUG_STATE={}
      MODEL_Q={ ["4|1|3|false|false|false"]={tab=10},
        ["4|1|1|false|false|false"]={berserk=10},
        ["4|0|3|false|false|false"]={wait=10} }
      function ready() calls=calls+1 end
      function c_save() return "" end
      function route_serialize() return "{}" end
      function say() end
      function level_key() return floor end
      function berserk_recovering() return false end
      function scan_hostiles()
        return {any=count>0,monsters=count>0 and {{x=distance,y=0,
          monster={name=function() return "Eustachio" end}}} or {}}
      end
      you={species=function() return "Minotaur" end,class=function() return "Berserker" end,
        turns=function() return tick end,hp=function() return hp,100 end,
        berserk=function() return false end,confused=function() return false end,
        feel_safe=function() return count==0 end,status=function() return "" end,
        poisoned=function() return false end,on_fire=function() return false end,
        activate_ability=function() action="berserk";return true end}
      crawl={take_note=function() end,do_commands=function(c) action=c[1] end}
    ''')
    lua.execute(hook)
    return lua


lua=vm();lua.execute('ready();assert(action=="CMD_AUTOFIGHT" and ML_EUSTACHIO.active)')
lua=vm();lua.execute('distance=1;ready();assert(action=="berserk")')
lua=vm();lua.execute('hp=50;ready();assert(calls==1 and not ML_EUSTACHIO.active)')
lua=vm();lua.execute('BOT.paused=true;ready();assert(calls==1 and not ML_EUSTACHIO.seen)')
lua=vm();lua.execute('ready();floor="D:5";ready();assert(calls==1 and not ML_EUSTACHIO.active)')
lua=vm();lua.execute('ready();for i=1,8 do ready() end;assert(calls==1 and not ML_EUSTACHIO.active)')
lua=vm();lua.execute('ready();count=0;for i=1,11 do tick=tick+1;ready() end;assert(calls==1 and not ML_EUSTACHIO.active)')
print('7 learned-hook regression cases passed')
