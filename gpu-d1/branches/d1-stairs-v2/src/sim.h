// Supported-rule extraction from Crawl (GPL-2.0-or-later); see SOURCES.md.
#pragma once
#include <stdint.h>
#ifdef __CUDACC__
#define HD __host__ __device__
#else
#define HD
#endif
namespace sim {
constexpr int N = 5600, W = 80, H = 70, MAX = 64;
HD inline int mn(int a, int b) { return a < b ? a : b; }
HD inline int mx(int a, int b) { return a > b ? a : b; }
HD inline int ab(int a) { return a < 0 ? -a : a; }
HD inline int cheb(int a, int b) { return mx(ab(a % W - b % W), ab(a / W - b / W)); }
HD inline uint64_t mix(uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}
struct RNG {
    uint64_t state, inc;
    HD uint32_t next() {
        uint64_t old = state;
        state = old * 6364136223846793005ULL + (inc | 1);
        uint32_t x = ((old >> 18) ^ old) >> 27, r = old >> 59;
        return (x >> r) | (x << ((-r) & 31));
    }
    HD void seed(uint64_t s, uint64_t seq) {
        state = 0;
        inc = (seq << 1) | 1;
        next();
        state += s;
        next();
    }
    HD int r(int bound) {
        if (bound <= 1)
            return 0;
        uint32_t x = next();
        uint64_t m = uint64_t(x) * uint32_t(bound);
        uint32_t low = m;
        if (low < uint32_t(bound)) {
            uint32_t t = uint32_t(-uint32_t(bound)) % uint32_t(bound);
            while (low < t) {
                x = next();
                m = uint64_t(x) * uint32_t(bound);
                low = m;
            }
        }
        return m >> 32;
    }
    HD int avg(int n) {
        int a = r(n);
        return (a + r(n + 1)) / 2;
    }
    HD int round(int n, int d) {
        int rem = n % d;
        return n / d + (rem && r(d) < rem);
    }
};
struct Kind {
    int speed, damage, tohit, bypass;
};
struct Config {
    int count, player, hp, ac100, ev100, sh100, shield_limit, regen, repair, gdr[2];
    Kind kinds[6];
};
struct Map {
    const uint8_t *floor;
    const uint16_t *dist;
    const uint32_t *los;
    const int16_t *starts;
};
struct Stats {
    uint64_t turns, actions, attacks, blocks, dodges, damage, deaths, resets, moves, repairs,
        stalls, move_turns, combat_turns;
};
struct World {
    RNG rng;
    int hp, regen, blocks, fixture;
    uint64_t episode;
    Stats s;
};
struct Access {
    int16_t *positions, *energies, *occupancy;
    int world, batch, count;
    bool tiled;
    HD int offset(int i) const { return tiled ? world * count + i : i * batch + world; }
    HD int16_t &pos(int i) { return positions[offset(i)]; }
    HD int16_t &energy(int i) { return energies[offset(i)]; }
    HD int16_t &occ(int p) { return occupancy[tiled ? world * N + p : p * batch + world]; }
};
HD inline void reset(World &w, Access &a, const Config &c, const Map &m, bool first = false) {
    if (!first)
        for (int i = 0; i < c.count; i++)
            a.occ(a.pos(i)) = -1;
    w.hp = c.hp;
    w.regen = 0;
    w.blocks = 0;
    // RNG continues across episodes: never replay identical combat randomness.
    for (int i = 0; i < c.count; i++) {
        int p = m.starts[w.fixture * MAX + i];
        a.pos(i) = p;
        a.occ(p) = i;
        a.energy(i) = 70 + w.rng.r(10);
    }
    if (!first) {
        w.episode++;
        w.s.resets++;
    }
}
HD inline void prepare(World &w, Access &a, const Config &c, const Map &m) {
    if (w.hp <= 0)
        reset(w, a, c, m);
    w.blocks = 0;
    w.regen += c.regen;
    while (w.regen >= 100) {
        w.hp = mn(c.hp, w.hp + 1);
        w.regen -= 100;
    }
    w.s.turns++;
}
HD inline bool visible(const Map &m, int origin, int target) {
    int dx = target % W - origin % W, dy = target / W - origin / W;
    if (ab(dx) > 8 || ab(dy) > 8)
        return false;
    int bit = (dy + 8) * 17 + dx + 8;
    return (m.los[origin * 10 + bit / 32] >> (bit % 32)) & 1;
}
HD inline void attack(World &w, const Config &c, int id) {
    auto &r = w.rng;
    const Kind &k = c.kinds[id % 6];
    w.s.attacks++;
    int hit = r.r(k.tohit + 1);
    int ev = r.round(c.ev100, 100);
    ev = r.avg(2 * ev);
    int margin = hit - ev;
    if (r.r(100) < 5)
        margin = (r.r(2) ? 1 : -1) * 1000;
    int bypass = r.r(k.bypass);
    int sh = r.round(c.sh100, 100);
    int block = r.avg(sh * 2) / 3 - 1;
    if (block >= bypass && w.blocks < c.shield_limit) {
        w.blocks++;
        w.s.blocks++;
        return;
    }
    if (margin < 0) {
        w.s.dodges++;
        return;
    }
    int damage = 1 + r.r(k.damage);
    int ac = r.round(c.ac100, 100);
    // Native GDR calls armour_class() again; keep the independent rounding.
    int gac = r.round(c.ac100, 100);
    int gdr = c.gdr[gac - c.ac100 / 100]; // Cached exact GDR for either rounded AC.
    int saved = r.r(ac + 1);
    int half = r.round(ac, 2);
    saved = mx(saved, mn(gdr * k.damage / 100, half));
    damage = mx(0, damage - saved);
    w.hp -= damage;
    w.s.damage += damage;
}
// Stable energy order is shared by both compact schedulers; native ties differ.
HD inline bool better(Access &a, int i, int j) {
    return j < 0 || a.energy(i) > a.energy(j) || (a.energy(i) == a.energy(j) && i < j);
}
HD inline int scan(Access &a, int n) {
    int best = -1;
    for (int i = 0; i < n; i++)
        if (a.energy(i) >= 80 && better(a, i, best))
            best = i;
    return best;
}
HD inline void push(int *heap, int &n, int id, Access &a) {
    int j = n++;
    while (j) {
        int p = (j - 1) / 2;
        if (!better(a, id, heap[p]))
            break;
        heap[j] = heap[p];
        j = p;
    }
    heap[j] = id;
}
HD inline int pop(int *heap, int &n, Access &a) {
    int out = heap[0], id = heap[--n], j = 0;
    while (j * 2 + 1 < n) {
        int k = j * 2 + 1;
        if (k + 1 < n && better(a, heap[k + 1], heap[k]))
            k++;
        if (!better(a, heap[k], id))
            break;
        heap[j] = heap[k];
        j = k;
    }
    if (n)
        heap[j] = id;
    return out;
}
HD inline int neighbor(int p, int d) {
    const int dx[8] = {0, 1, 0, -1, 1, 1, -1, -1};
    const int dy[8] = {-1, 0, 1, 0, -1, 1, 1, -1};
    int x = p % W + dx[d], y = p / W + dy[d];
    return x >= 0 && x < W && y >= 0 && y < H ? y * W + x : -1;
}
HD inline int choose_move(World &w, Access &a, const Config &c, const Map &m, int id) {
    int p = a.pos(id), best = -1, bd = m.dist[p], ties = 0, rotation = w.rng.r(4);
    for (int z = 0; z < 8; z++) {
        int d = z < 4 ? (z + rotation) % 4 : 4 + (z + rotation) % 4;
        int q = neighbor(p, d);
        if (q < 0 || !m.floor[q] || q == c.player || a.occ(q) >= 0)
            continue;
        int dist = m.dist[q];
        if (dist < bd) {
            bd = dist;
            best = q;
            ties = 1;
        } else if (dist == bd && best >= 0 && w.rng.r(++ties) == 0)
            best = q;
    }
    if (best >= 0 || !c.repair)
        return best;
    // Skip searches when completely surrounded. A bounded 24-node BFS may detour
    // around a blocker; it must reach a cell with lower static distance.
    int cells[24], first[24], len = 1;
    cells[0] = p;
    first[0] = -1;
    w.s.repairs++;
    for (int head = 0; head < len; head++)
        for (int d = 0; d < 8; d++) {
            int q = neighbor(cells[head], d);
            if (q < 0 || !m.floor[q] || q == c.player || a.occ(q) >= 0)
                continue;
            bool seen = false;
            for (int j = 0; j < len; j++)
                if (cells[j] == q) {
                    seen = true;
                    break;
                }
            if (seen)
                continue;
            int step = head == 0 ? q : first[head];
            if (m.dist[q] < m.dist[p])
                return step;
            if (len < 24) {
                cells[len] = q;
                first[len] = step;
                len++;
            }
        }
    return -1;
}
HD inline void act(World &w, Access &a, const Config &c, const Map &m, int id) {
    w.s.actions++;
    a.energy(id) -= 10;
    if (cheb(a.pos(id), c.player) == 1) {
        attack(w, c, id);
        return;
    }
    int q = choose_move(w, a, c, m, id);
    if (q >= 0) {
        a.occ(a.pos(id)) = -1;
        a.pos(id) = q;
        a.occ(q) = id;
        w.s.moves++;
    } else
        w.s.stalls++;
}
HD inline void finish(World &w, uint64_t moves, uint64_t attacks) {
    w.s.move_turns += (w.s.moves != moves);
    w.s.combat_turns += (w.s.attacks != attacks);
    if (w.hp <= 0)
        w.s.deaths++;
}
template <bool Heap> HD inline void step(World &w, Access &a, const Config &c, const Map &m) {
    prepare(w, a, c, m);
    uint64_t moves = w.s.moves, attacks = w.s.attacks;
    for (int i = 0; i < c.count; i++)
        a.energy(i) += c.kinds[i % 6].speed;
    int heap[MAX], n = 0;
    if (Heap)
        for (int i = 0; i < c.count; i++)
            if (a.energy(i) >= 80)
                push(heap, n, i, a);
    while (w.hp > 0) {
        int id = Heap ? (n ? pop(heap, n, a) : -1) : scan(a, c.count);
        if (id < 0)
            break;
        act(w, a, c, m, id);
        if (Heap && a.energy(id) >= 80)
            push(heap, n, id, a);
    }
    finish(w, moves, attacks);
}
HD inline void observe(const World &w, Access &a, const Config &c, const Map &m, int16_t *out) {
    out[0] = w.hp;
    out[1] = w.blocks;
    for (int i = 0; i < c.count; i++)
        out[i + 2] = visible(m, c.player, a.pos(i)) ? a.pos(i) : -1;
}
} // namespace sim
