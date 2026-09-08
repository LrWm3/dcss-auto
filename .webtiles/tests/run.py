"""Run RC regression suites in independent Lua VMs: uv run --with lupa python .webtiles/tests/run.py"""
from pathlib import Path
from lupa import LuaRuntime

here = Path(__file__).resolve().parent
source = (here.parent / 'rcs' / 'codex-autocrawl.rc').read_text()
lua_source = source.split('\n<\n', 1)[1].rsplit('\n>', 1)[0]
tests = sorted(here.glob('*.lua'))
for test in tests:
    lua = LuaRuntime()
    lua.execute('crawl={more_autoclear=function() end}; add_autopickup_func=function() end')
    lua.execute(lua_source)
    lua.execute(test.read_text())
print(f'{len(tests)} suites passed')
