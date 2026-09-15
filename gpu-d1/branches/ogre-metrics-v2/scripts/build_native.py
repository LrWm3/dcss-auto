#!/usr/bin/env python3
"""Reproducible instrumented copy. Never modify the repository's native tree."""
import hashlib
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent/'crawl-0.35/crawl-ref/source'
DEST = ROOT/'native/source'

def main():
    if not DEST.exists():
        DEST.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['cp','-a','--reflink=auto',str(SOURCE),str(DEST)],check=True)
    hashes = {}
    def patch(name, edits=(), suffix='', hook=False):
        data = (SOURCE/name).read_text()
        hashes[name] = hashlib.sha256((SOURCE/name).read_bytes()).hexdigest()
        if hook:
            data = data.replace('#include "AppHdr.h"', '#include "AppHdr.h"\n#include "../../src/native_hooks.h"', 1)
        for old, new in edits:
            assert data.count(old) == 1, (name, old, data.count(old))
            data = data.replace(old, new, 1)
        data += suffix
        target = DEST/name
        if not target.exists() or target.read_text() != data:
            target.write_text(data)
    patch('l-debug.cc', [('const struct luaL_Reg debug_dlib[] =', '#include "../../src/native.inc"\n#include "../../src/native_bench.inc"\nconst struct luaL_Reg debug_dlib[] ='),
                         ('const struct luaL_Reg debug_dlib[] =\n{','const struct luaL_Reg debug_dlib[] =\n{\n{ "gpu_export", gpu_export },\n{ "gpu_bench", gpu_bench },')])
    patch('los.cc', suffix='\n#include "../../src/native_rays.inc"\n')
    patch('attack.h', [('class attack\n{','class attack\n{\nfriend struct gpu_native_access;')])
    patch('melee-attack.h', [('class melee_attack : public attack\n{','class melee_attack : public attack\n{\nfriend struct gpu_native_access;')])
    patch('attack.cc', [('void attack::handle_phase_blocked()\n{','void attack::handle_phase_blocked()\n{\n    if (gpu_d1_active && defender->is_player()) gpu_d1_stats.blocks++;')], hook=True)
    patch('melee-attack.cc', [('    const int ev = defender->evasion(false, attacker);','    if (gpu_d1_active && defender && defender->is_player()) {gpu_d1_stats.attacks++; needs_message=false;}\n    const int ev = defender->evasion(false, attacker);'),
                            ('void melee_attack::handle_phase_dodged()\n{','void melee_attack::handle_phase_dodged()\n{\n    if (gpu_d1_active && defender->is_player()) gpu_d1_stats.dodges++;')], hook=True)
    patch('ouch.cc', [('    int drain_amount = 0;', '    if (gpu_d1_active) { gpu_d1_stats.damage += max(0,dam); you.hp -= max(0,dam); if (you.hp <= 0) throw gpu_d1_terminal{}; return; }\n    int drain_amount = 0;')], hook=True)
    patch('mon-act.cc', [('            handle_monster_move(mon);\n            _post_monster_move(mon);',
                          '            const coord_def gpu_oldpos=mon->pos();\n            if(gpu_d1_active) {gpu_d1_stats.actions++;mon->behaviour=BEH_SEEK;mon->foe=MHITYOU;mon->target=you.pos();mon->foe_memory=1000;}\n            handle_monster_move(mon);\n            if(gpu_d1_active && mon->pos()!=gpu_oldpos) gpu_d1_stats.moves++;\n            _post_monster_move(mon);')],
          suffix='\nvoid gpu_native_clear_queue() { while(!monster_queue.empty()) monster_queue.pop(); }\n',hook=True)
    patch('message.cc', [('                 bool cap)\n{', '                 bool cap)\n{\n    if (gpu_d1_active) return;')],hook=True)
    # Sound has no role in fixed-awareness fixtures.
    patch('shout.cc', [('bool noisy(int original_loudness, const coord_def& where,','bool noisy(int original_loudness, const coord_def& where,')],hook=True)
    data=(DEST/'shout.cc').read_text()
    start=data.index('bool noisy(int original_loudness,')
    brace=data.index('{',start)
    data=data[:brace+1]+'\n    if (gpu_d1_active) return false;'+data[brace+1:]
    (DEST/'shout.cc').write_text(data)
    (DEST/'util/release_ver').write_text('0.35-a0\n')
    (DEST/'scripts/gpu_export.lua').write_text('local a=script.simple_args()\ndebug.gpu_export(a[1])\n')
    (DEST/'scripts/gpu_bench.lua').write_text('local a=script.simple_args()\ndebug.gpu_bench(a[1], tonumber(a[2]), tonumber(a[3]), a[4])\n')
    (ROOT/'results/native-source-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
    subprocess.run(['make','-C',str(DEST),'-j4','GAME=crawl-gpu-d1','crawl-gpu-d1'],check=True)

if __name__ == '__main__':main()
