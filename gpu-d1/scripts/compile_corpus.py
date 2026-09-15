#!/usr/bin/env python3
"""Compile exported native D:1 layouts into compact resident-map files.

The compiler keeps only immutable geometry and shortest-path tables.  Dynamic
actors, occupancy, RNG and awareness remain in the learning environment.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import struct

N, W, H = 5600, 80, 70
MAGIC = 0x44325650


def compile_one(source: pathlib.Path, target: pathlib.Path):
    data = json.loads(source.with_suffix('.json').read_text())
    if data['unsupported_tiles']:
        raise ValueError(f'{source}: unsupported terrain')
    markers = source.with_suffix('.markers').read_text().splitlines()
    if any(line.split()[0] != '0' for line in markers):
        raise ValueError(f'{source}: active map marker')
    floor = bytes(c == '.' for row in data['map'] for c in row)
    if len(floor) != N:
        raise ValueError(f'{source}: unexpected map size')

    def neighbors(p):
        x, y = p % W, p // W
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0),
                       (1, -1), (1, 1), (-1, 1), (-1, -1)):
            qx, qy = x + dx, y + dy
            if 0 <= qx < W and 0 <= qy < H:
                q = qy * W + qx
                if floor[q]:
                    yield q

    cells = [p for p in range(N) if floor[p]]
    index = [-1] * N
    for i, p in enumerate(cells):
        index[p] = i
    distances = []
    for source_cell in cells:
        dist = [65535] * N
        dist[source_cell] = 0
        queue = collections.deque([source_cell])
        while queue:
            p = queue.popleft()
            for q in neighbors(p):
                if dist[q] == 65535:
                    dist[q] = dist[p] + 1
                    queue.append(q)
        distances.extend(dist)

    rays = iter(source.with_suffix('.rays').read_text().splitlines())
    ray_count = int(next(rays))
    ends = [tuple(map(int, next(rays).split())) for _ in range(ray_count)]
    blockers = []
    for line in rays:
        x, y, inside, bits = line.split()
        if int(inside):
            blockers.append((int(x), int(y), int(bits[::-1], 2)))
    native_los = source.with_suffix('.los').read_bytes()
    if len(native_los) != N * 289:
        raise ValueError(f'{source}: missing native LOS table')
    masks = []
    for p in range(N):
        px, py = p % W, p // W
        seen = 1 << 144
        for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
            dead = 0
            for x, y, bits in blockers:
                qx, qy = px + sx * x, py + sy * y
                if 0 <= qx < W and 0 <= qy < H and not floor[qy * W + qx]:
                    dead |= bits
            for i, (x, y) in enumerate(ends):
                qx, qy = px + sx * x, py + sy * y
                if not (dead >> i) & 1 and 0 <= qx < W and 0 <= qy < H:
                    if any(x == bx and y == by for bx, by, _ in blockers):
                        seen |= 1 << ((sy * y + 8) * 17 + sx * x + 8)
        expected = sum(int(v) << i for i, v in enumerate(native_los[p * 289:(p + 1) * 289]))
        if seen != expected:
            raise ValueError(f'{source}: LOS mismatch at {p}')
        masks.extend((seen >> (32 * i)) & 0xffffffff for i in range(10))

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('wb') as out:
        out.write(struct.pack('<3I', MAGIC, data['seed'], len(cells)))
        out.write(struct.pack('<4i', data['hp'], data['ac100'], data['ev100'], data['sh100']))
        out.write(floor)
        out.write(struct.pack(f'<{N}h', *cells, *([-1] * (N - len(cells)))))
        out.write(struct.pack(f'<{N}h', *index))
        out.write(struct.pack(f'<{len(distances)}H', *distances))
        out.write(struct.pack(f'<{N * 10}I', *masks))
    return dict(seed=data['seed'], cells=len(cells), sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                player_hp=data['hp'], monster_roster=data['roster'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sources', type=pathlib.Path, action='append', required=True,
                    help='directory containing native-SEED.{json,markers,rays,los}; repeat for multiple export batches')
    ap.add_argument('--output', type=pathlib.Path, required=True)
    ap.add_argument('--seeds', default='1057,1080,1235,1363,1589,1609')
    args = ap.parse_args()
    rows = []
    for seed in map(int, args.seeds.split(',')):
        source = next((root / f'native-{seed}' for root in args.sources
                       if (root / f'native-{seed}.json').exists()), None)
        if source is None:
            raise FileNotFoundError(f'no native export for seed {seed} in {args.sources}')
        rows.append(compile_one(source, args.output / f'map-{seed}.bin'))
    (args.output / 'manifest.json').write_text(json.dumps({
        'format': 'gpu-d1-v2-map-corpus', 'magic': MAGIC, 'maps': rows,
        'sources': args.seeds, 'static_only': True,
    }, indent=2) + '\n')
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
