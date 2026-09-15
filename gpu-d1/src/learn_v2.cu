// Multi-map floor-clear proxy with sleep and explicit variable statistics.
// This is an experiment task, not a claim of native Crawl semantics.
#include "sim.h"
#include <cuda_runtime.h>
#include <cassert>
#include <cstdint>

namespace learn_v2 {
constexpr int ENEMIES = 8, OBS = 250, OUT = 12;

struct V2Config {
    int count, sleep_radius, stat_mode, player_mode;
    int player_hp, player_damage_min, player_damage_max, player_hit;
};
struct V2Tables {
    // Map data is flattened by map. Pointer tables scale poorly on CUDA
    // because the whole table is passed as a kernel argument; these flat
    // buffers keep the argument small while allowing arbitrarily many maps.
    const uint8_t *floor;
    const int16_t *cells, *index;
    const uint16_t *distance;
    const uint32_t *los;
    const int *ncells, *distance_offsets;
    int n_maps;
};
struct State {
    sim::World w;
    int map_id, player, ticks, killed, damage_taken;
    int player_max_hp, player_damage_min, player_damage_max, player_hit;
    int16_t pos[ENEMIES], energy[ENEMIES], hp[ENEMIES], max_hp[ENEMIES];
    int16_t damage[ENEMIES], speed[ENEMIES], hit[ENEMIES], awake[ENEMIES];
    int16_t occ[sim::N];
};

HD inline const uint8_t *fl(const V2Tables &t, int m) { return t.floor + m * sim::N; }
HD inline bool tile(const V2Tables &t, int m, int p) { return p >= 0 && p < sim::N && fl(t, m)[p]; }
HD inline const uint16_t *field(const V2Tables &t, int m, int source) {
    int16_t row = t.index[m * sim::N + source];
    // The full 388-map distance buffer is larger than 2^31 elements; force
    // 64-bit pointer arithmetic before multiplying by the per-map row width.
    return row < 0 ? nullptr : t.distance + (size_t(t.distance_offsets[m]) + size_t(row)) * sim::N;
}
HD inline int16_t &occ(State &s, int p) { return s.occ[p]; }
HD inline int neighbor_v2(int p, int d) { return sim::neighbor(p, d); }

HD inline void assign_stats(State &s, const V2Config &c, int i) {
    int a = c.stat_mode == 0 ? 0 : i % 4;
    // Mode 1 is the training set. Mode 2 keeps the same four roles but shifts
    // their strengths, providing a small held-out encounter-strength test.
    const int maxhp[2][4] = {{8, 24, 6, 16}, {10, 32, 4, 20}};
    const int dmg[2][4] = {{3, 8, 2, 5}, {4, 10, 1, 6}};
    const int speed[2][4] = {{10, 5, 20, 10}, {10, 5, 20, 10}};
    const int hit[2][4] = {{65, 75, 50, 70}, {60, 80, 45, 75}};
    int mode = c.stat_mode == 2 ? 1 : 0;
    s.max_hp[i] = maxhp[mode][a];
    s.hp[i] = s.max_hp[i];
    s.damage[i] = dmg[mode][a];
    s.speed[i] = speed[mode][a];
    s.hit[i] = hit[mode][a];
}

HD inline void reset(State &s, const V2Config &c, const V2Tables &t) {
    s.map_id = s.w.rng.r(t.n_maps);
    int m = s.map_id;
    for (int p = 0; p < sim::N; p++) s.occ[p] = -1;
    s.player = t.cells[m * sim::N + s.w.rng.r(t.ncells[m])];
    s.player_max_hp = c.player_hp;
    s.player_damage_min = c.player_damage_min;
    s.player_damage_max = c.player_damage_max;
    s.player_hit = c.player_hit;
    if (c.player_mode) {
        int spread = c.player_mode == 2 ? 6 : 4;
        s.player_max_hp += s.w.rng.r(2 * spread + 1) - spread;
        int damage_spread = c.player_mode == 2 ? 3 : 2;
        s.player_damage_max += s.w.rng.r(2 * damage_spread + 1) - damage_spread;
        s.player_damage_max = sim::mx(s.player_damage_min + 1, s.player_damage_max);
        int hit_spread = c.player_mode == 2 ? 15 : 10;
        s.player_hit += s.w.rng.r(2 * hit_spread + 1) - hit_spread;
    }
    s.w.hp = s.player_max_hp;
    s.w.regen = 0;
    s.ticks = s.killed = s.damage_taken = 0;
    for (int i = 0; i < c.count; i++) {
        int p;
        do p = t.cells[m * sim::N + s.w.rng.r(t.ncells[m])];
        while (p == s.player || s.occ[p] >= 0);
        s.pos[i] = p;
        s.occ[p] = i;
        s.energy[i] = 0;
        s.awake[i] = 0;
        assign_stats(s, c, i);
    }
    for (int i = c.count; i < ENEMIES; i++) {
        s.pos[i] = -1; s.energy[i] = -30000; s.hp[i] = 0; s.max_hp[i] = 0;
        s.damage[i] = s.speed[i] = s.hit[i] = s.awake[i] = 0;
    }
}

HD inline void wake_nearby(State &s, const V2Config &c) {
    for (int i = 0; i < c.count; i++) if (s.hp[i] > 0 && !s.awake[i]) {
        if (sim::cheb(s.player, s.pos[i]) <= c.sleep_radius) {
            s.awake[i] = 1;
            s.energy[i] = 70; // no stored actions while asleep
        }
    }
}

HD inline void monster_attack(State &s, int i) {
    if (s.w.rng.r(100) >= s.hit[i]) return;
    int damage = 1 + s.w.rng.r(s.damage[i]);
    s.w.hp -= damage;
    s.damage_taken += damage;
}

HD inline int choose_move(State &s, const V2Config &c, const V2Tables &t, int i) {
    const uint16_t *ds = field(t, s.map_id, s.player);
    if (!ds) return -1;
    int p = s.pos[i], best = -1, bd = ds[p], ties = 0;
    int rotation = s.w.rng.r(4);
    for (int z = 0; z < 8; z++) {
        int d = z < 4 ? (z + rotation) % 4 : 4 + (z + rotation) % 4;
        int q = neighbor_v2(p, d);
        if (!tile(t, s.map_id, q) || q == s.player || s.occ[q] >= 0) continue;
        int dist = ds[q];
        if (dist < bd) { bd = dist; best = q; ties = 1; }
        else if (dist == bd && best >= 0 && s.w.rng.r(++ties) == 0) best = q;
    }
    return best;
}

HD inline void monster_step(State &s, const V2Config &c, const V2Tables &t, int i) {
    s.energy[i] -= 10;
    if (sim::cheb(s.pos[i], s.player) == 1) {
        monster_attack(s, i);
        return;
    }
    int q = choose_move(s, c, t, i);
    if (q >= 0) { s.occ[s.pos[i]] = -1; s.pos[i] = q; s.occ[q] = i; }
}

HD inline int scan_v2(const State &s, const V2Config &c) {
    int best = -1;
    for (int i = 0; i < c.count; i++) if (s.hp[i] > 0 && s.awake[i] && s.energy[i] >= 80)
        if (best < 0 || s.energy[i] > s.energy[best] ||
            (s.energy[i] == s.energy[best] && i < best)) best = i;
    return best;
}

HD inline void observe(const State &s, const V2Config &c, const V2Tables &t, float *o, float *mask) {
    for (int j = 0; j < OBS; j++) o[j] = 0;
    int m = s.map_id;
    for (int y = -4; y <= 4; y++) for (int x = -4; x <= 4; x++) {
        int px = s.player % sim::W + x, py = s.player / sim::W + y, j = (y + 4) * 9 + x + 4;
        if (px < 0 || px >= sim::W || py < 0 || py >= sim::H) continue;
        int p = py * sim::W + px;
        o[j] = tile(t, m, p);
        int id = s.occ[p];
        if (id >= 0) o[81 + j] = s.awake[id] ? s.hp[id] / float(s.max_hp[id]) : 0.2f;
    }
    for (int i = 0; i < c.count; i++) if (s.hp[i] > 0) {
        int j = 162 + i * 10;
        o[j] = (s.pos[i] % sim::W - s.player % sim::W) / 80.f;
        o[j + 1] = (s.pos[i] / sim::W - s.player / sim::W) / 70.f;
        o[j + 2] = s.hp[i] / float(s.max_hp[i]);
        o[j + 3] = s.max_hp[i] / 32.f;
        o[j + 4] = s.damage[i] / 12.f;
        o[j + 5] = s.speed[i] / 20.f;
        o[j + 6] = s.hit[i] / 100.f;
        o[j + 7] = s.awake[i];
        o[j + 8] = 1;
        o[j + 9] = sim::mx(0, s.energy[i]) / 100.f;
    }
    o[242] = s.w.hp / float(s.player_max_hp);
    o[243] = s.player_max_hp / 32.f;
    o[244] = s.player_damage_min / 8.f;
    o[245] = s.player_damage_max / 8.f;
    o[246] = s.player_hit / 100.f;
    o[247] = s.ticks / 512.f;
    o[248] = s.player % sim::W / 80.f;
    o[249] = s.player / sim::W / 70.f;
    for (int d = 0; d < 8; d++) { int q = neighbor_v2(s.player, d); mask[d] = tile(t, m, q); }
    mask[8] = 1;
}

HD inline void transition(State &s, const V2Config &c, const V2Tables &t, int action, int limit, float *out) {
    for (int j = 0; j < OUT; j++) out[j] = 0;
    float reward = -0.001f;
    s.w.regen += 23;
    while (s.w.regen >= 100) { s.w.hp = sim::mn(s.player_max_hp, s.w.hp + 1); s.w.regen -= 100; }
    if (action >= 0 && action < 8) {
        int p = neighbor_v2(s.player, action);
        if (tile(t, s.map_id, p)) {
            int id = s.occ[p];
            if (id >= 0) {
                if (s.w.rng.r(100) < s.player_hit) {
                    s.hp[id] -= s.player_damage_min + s.w.rng.r(s.player_damage_max - s.player_damage_min + 1);
                    if (s.hp[id] <= 0) { s.hp[id] = 0; s.occ[p] = -1; s.energy[id] = -30000; s.killed++; reward += 1; }
                }
            } else s.player = p;
        }
    }
    wake_nearby(s, c);
    for (int i = 0; i < c.count; i++) if (s.hp[i] > 0 && s.awake[i]) s.energy[i] += s.speed[i];
    while (s.w.hp > 0) {
        int id = scan_v2(s, c);
        if (id < 0) break;
        monster_step(s, c, t, id);
    }
    s.ticks++;
    bool clear = s.killed == c.count, death = s.w.hp <= 0;
    bool timeout = !clear && !death && s.ticks >= limit;
    if (clear) reward += 3;
    if (death) reward -= 1;
    int awake_count = 0; for (int i = 0; i < c.count; i++) awake_count += s.awake[i] && s.hp[i] > 0;
    out[0] = reward; out[1] = clear || death || timeout; out[2] = clear; out[3] = s.killed;
    out[4] = sim::mx(0, s.w.hp); out[5] = s.ticks; out[6] = death; out[7] = timeout;
    out[8] = awake_count; out[9] = s.damage_taken; out[10] = s.map_id; out[11] = s.player_max_hp;
    if (out[1]) { s.w.episode++; reset(s, c, t); }
}

__global__ void init_kernel(State *s, int n, V2Config c, V2Tables t, uint64_t seed, float *o, float *mask) {
    int i = blockIdx.x * blockDim.x + threadIdx.x; if (i >= n) return;
    s[i] = {}; s[i].w.rng.seed(sim::mix(seed + i), i + 1); reset(s[i], c, t); observe(s[i], c, t, o + i * OBS, mask + i * 9);
}
__global__ void step_kernel(State *s, int n, V2Config c, V2Tables t, const int64_t *a, int limit, float *o, float *mask, float *out) {
    int i = blockIdx.x * blockDim.x + threadIdx.x; if (i >= n) return;
    transition(s[i], c, t, int(a[i]), limit, out + i * OUT); observe(s[i], c, t, o + i * OBS, mask + i * 9);
}
HD inline int heuristic(State &s, const V2Config &c, const V2Tables &t) {
    int best = -1, hp = 100000;
    for (int d = 0; d < 8; d++) {
        int q = neighbor_v2(s.player, d);
        if (q >= 0 && s.occ[q] >= 0 && s.hp[s.occ[q]] < hp) { hp = s.hp[s.occ[q]]; best = d; }
    }
    if (best >= 0) return best;
    const uint16_t *from_player = field(t, s.map_id, s.player);
    int target = -1, distance = 65535;
    for (int i = 0; i < c.count; i++) if (s.hp[i] > 0 && from_player[s.pos[i]] < distance) {
        distance = from_player[s.pos[i]]; target = s.pos[i];
    }
    if (target < 0) return 8;
    const uint16_t *from_target = field(t, s.map_id, target);
    distance = from_target[s.player]; best = 8;
    for (int d = 0; d < 8; d++) {
        int q = neighbor_v2(s.player, d);
        if (tile(t, s.map_id, q) && from_target[q] < distance) { distance = from_target[q]; best = d; }
    }
    return best;
}
__global__ void heuristic_kernel(State *s, int n, V2Config c, V2Tables t, int64_t *a) {
    int i = blockIdx.x * blockDim.x + threadIdx.x; if (i < n) a[i] = heuristic(s[i], c, t);
}
}
using namespace learn_v2;
extern "C" {
int learn_v2_state_bytes() { return sizeof(State); }
int learn_v2_obs_size() { return OBS; }
int learn_v2_out_size() { return OUT; }
int learn_v2_config_bytes() { return sizeof(V2Config); }
int learn_v2_init(void *raw, int n, V2Config *c, V2Tables *t, uint64_t seed, float *o, float *mask, void *stream, int gpu) {
    State *s = static_cast<State *>(raw);
    if (gpu) { init_kernel<<<(n + 127) / 128, 128, 0, (cudaStream_t)stream>>>(s, n, *c, *t, seed, o, mask); return cudaGetLastError(); }
    for (int i = 0; i < n; i++) { s[i] = {}; s[i].w.rng.seed(sim::mix(seed + i), i + 1); reset(s[i], *c, *t); observe(s[i], *c, *t, o + i * OBS, mask + i * 9); } return 0;
}
int learn_v2_step(void *raw, int n, V2Config *c, V2Tables *t, const int64_t *a, int limit, float *o, float *mask, float *out, void *stream, int gpu) {
    State *s = static_cast<State *>(raw);
    if (gpu) { step_kernel<<<(n + 127) / 128, 128, 0, (cudaStream_t)stream>>>(s, n, *c, *t, a, limit, o, mask, out); return cudaGetLastError(); }
    for (int i = 0; i < n; i++) { transition(s[i], *c, *t, int(a[i]), limit, out + i * OUT); observe(s[i], *c, *t, o + i * OBS, mask + i * 9); } return 0;
}
int learn_v2_heuristic(void *raw, int n, V2Config *c, V2Tables *t, int64_t *a, void *stream, int gpu) {
    State *s = static_cast<State *>(raw);
    if (gpu) { heuristic_kernel<<<(n + 127) / 128, 128, 0, (cudaStream_t)stream>>>(s, n, *c, *t, a); return cudaGetLastError(); }
    for (int i = 0; i < n; i++) a[i] = heuristic(s[i], *c, *t); return 0;
}
}
