#!/usr/bin/env python3
"""Compile a native export; independently flatten and verify native ray LOS."""
import collections
import hashlib
import json
import pathlib
import struct
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]

def main():
    before = time.perf_counter()
    source = ROOT / 'fixtures/native-1057'
    d = json.loads(source.with_suffix('.json').read_text())
    assert d['unsupported_tiles'] == 0
    markers = source.with_suffix('.markers').read_text().splitlines()
    assert all(line.split()[0] == '0' for line in markers), 'Active/non-feature map marker'
    floor = bytes(c == '.' for c in ''.join(d['map']))
    lines = iter(source.with_suffix('.rays').read_text().splitlines())
    nr = int(next(lines))
    ends = [tuple(map(int, next(lines).split())) for _ in range(nr)]
    blockers = []
    for line in lines:
        x, y, inside, bits = line.split()
        if int(inside):
            blockers.append((int(x), int(y), int(bits[::-1], 2)))
    native = source.with_suffix('.los').read_bytes()
    assert len(native) == 5600 * 289
    masks = []
    for p in range(5600):
        px, py = p % 80, p // 80
        seen = 1 << 144
        for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            dead = 0
            for x, y, bits in blockers:
                qx, qy = px + sx*x, py + sy*y
                if 0 <= qx < 80 and 0 <= qy < 70 and not floor[qy*80+qx]:
                    dead |= bits
            for i, (x, y) in enumerate(ends):
                qx, qy = px + sx*x, py + sy*y
                if not (dead >> i) & 1 and 0 <= qx < 80 and 0 <= qy < 70:
                    # Endpoint radius is checked separately, just as in Crawl.
                    if any(x == bx and y == by for bx, by, _ in blockers):
                        seen |= 1 << ((sy*y+8)*17+sx*x+8)
        expected = sum(int(v) << i for i, v in enumerate(native[p*289:(p+1)*289]))
        assert seen == expected, f'LOS mismatch origin {p}: {(seen ^ expected).bit_count()} cells'
        masks.extend((seen >> (32*i)) & 0xffffffff for i in range(10))

    def neighbors(p):
        x, y = p % 80, p // 80
        for dx, dy in ((0,-1),(1,0),(0,1),(-1,0),(1,-1),(1,1),(-1,1),(-1,-1)):
            if 0 <= x+dx < 80 and 0 <= y+dy < 70:
                q = (y+dy)*80+x+dx
                if floor[q]:
                    yield q

    # Deterministic geometric predicate, independent of measured performance.
    candidates = [p for p in range(5600) if floor[p] and len(list(neighbors(p))) == 8]
    player = min(candidates, key=lambda p: (abs(p%80-40)+abs(p//80-35), p))
    dist = [65535]*5600
    dist[player] = 0
    queue = collections.deque([player])
    while queue:
        p = queue.popleft()
        for q in neighbors(p):
            if dist[q] == 65535:
                dist[q] = dist[p]+1
                queue.append(q)
    reachable = [p for p in range(5600) if 0 < dist[p] < 65535]
    assert len(reachable) >= 128
    contact = sorted(reachable, key=lambda p: (dist[p], p))[:64]
    approach = sorted((p for p in reachable if dist[p] >= 10), key=lambda p: (abs(dist[p]-18), p))[:64]
    assert len(approach) == 64 and len(set(approach)) == 64
    out = bytearray(struct.pack('<I8i', 0x44314750, player, *(d[k] for k in ('hp','ac100','ev100','sh100','shield_limit','regen')), 0))
    for k in d['roster']:
        out += struct.pack('<4i', *(k[v] for v in ('speed','damage','to_hit','bypass')))
    out += floor + struct.pack('<5600H', *dist) + struct.pack('<56000I', *masks)
    out += struct.pack('<128h', *(contact+approach))
    (ROOT/'fixtures/fixture.bin').write_bytes(out)
    manifest = dict(native_seed=d['seed'], fixture_sha256=hashlib.sha256(out).hexdigest(),
        native_sha256=hashlib.sha256(source.with_suffix('.json').read_bytes()).hexdigest(),
        native_map_markers=markers,
        player_position=[player%80,player//80], reachable_floor_cells=len(reachable)+1,
        contact_positions=[[p%80,p//80] for p in contact],
        approach_positions=[[p%80,p//80] for p in approach],
        approach_distances=[dist[p] for p in approach],
        los_checked_pairs=5600*289, los_mismatches=0, native_ray_count=nr,
        compile_seconds=time.perf_counter()-before,
        changes=['Geometry unchanged; stairs/exit inert.', 'Player relocated to selected floor cell.',
                 'Replace native monsters with 0–64 unarmed monsters cycling through the six exported species.',
                 'All monsters awake, hostile, permanently targeting the stationary player.',
                 'Monster HP is omitted because this workload cannot damage monsters.',
                 'Energy starts at 70 + uniform[0,9]; RNG continues across episode resets.',
                 'No Zot clock or other long-term world effects; recorded deaths are combat deaths.',
                 'Native floor items retained in raw snapshot but inert and absent from hot state.'])
    (ROOT/'fixtures/manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    rows = [list(row) for row in d['map']]
    for p in approach: rows[p//80][p%80] = 'a'
    for p in contact: rows[p//80][p%80] = 'c'
    rows[player//80][player%80] = '@'
    (ROOT/'fixtures/map.txt').write_text('\n'.join(map(''.join, rows))+'\n\n@ player; c contact spawn; a approach spawn. These are alternate populations.\n')
    print(json.dumps({k:manifest[k] for k in ('native_seed','player_position','reachable_floor_cells','los_checked_pairs','los_mismatches','compile_seconds')}))

if __name__ == '__main__':
    main()
