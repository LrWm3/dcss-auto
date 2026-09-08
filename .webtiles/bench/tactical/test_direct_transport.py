"""uv run --with lupa python .webtiles/bench/tactical/test_direct_transport.py"""
from pathlib import Path
from lupa import LuaRuntime

source=(Path(__file__).parent/'direct_transport.lua').read_text()
for key in (122,27,97):
    lua=LuaRuntime()
    lua.execute('''
    TB={active=true,seq=7,reported=7};calls=0
    ready=function() calls=calls+1 end
    tb_request=function(a) requested=a end
    you={turn_is_over=function() return false end}
    crawl={redraw_screen=function() end,getch=function() return key end,
      do_commands=function(c)
        command=c[1];assert(TB.reported==nil,"reload must publish initial state")
      end}
    ''')
    lua.globals().key=key
    lua.execute(source);lua.execute('ready()')
    g=lua.globals()
    if key==122:
        assert g.command=='CMD_SAVE_GAME_NOW' and g.TB.seq==7 and g.calls==1
    elif key==27:assert g.command is None and g.requested is None
    else:assert g.requested=='baseline' and g.calls==2
print('3 direct transport cases passed')
