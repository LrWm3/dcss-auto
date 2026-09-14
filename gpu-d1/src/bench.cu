#include "sim.h"
#include <cuda_runtime.h>
#include <omp.h>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
using namespace sim;
#define CUDA(x)                                                                                    \
    do {                                                                                           \
        cudaError_t e = (x);                                                                       \
        if (e != cudaSuccess)                                                                      \
            throw std::runtime_error(std::string(#x) + ": " + cudaGetErrorString(e));              \
    } while (0)
template <bool Heap>
__global__ void thread_run(World *worlds, Access base, Config c, Map m, int steps, int16_t *obs) {
    int id = blockIdx.x * blockDim.x + threadIdx.x;
    if (id >= base.batch)
        return;
    Access a = base;
    a.world = id;
    World w = worlds[id];
    for (int k = 0; k < steps; k++) {
        step<Heap>(w, a, c, m);
        if (obs)
            observe(w, a, c, m, obs + id * (c.count + 2));
    }
    worlds[id] = w;
}
template <bool Heap>
__global__ void warp_run(World *worlds, Access base, Config c, Map m, int steps, int16_t *obs) {
    int tid = blockIdx.x * blockDim.x + threadIdx.x, id = tid / 32, lane = tid % 32;
    if (id >= base.batch)
        return;
    Access a = base;
    a.world = id;
    World w;
    if (!lane)
        w = worlds[id];
    for (int k = 0; k < steps; k++) {
        if (Heap) {
            if (!lane)
                step<true>(w, a, c, m);
            __syncwarp();
        } else {
            uint64_t moves = 0, attacks = 0;
            if (!lane) {
                prepare(w, a, c, m);
                moves = w.s.moves;
                attacks = w.s.attacks;
            }
            __syncwarp();
            for (int i = lane; i < c.count; i += 32)
                a.energy(i) += c.kinds[i % 6].speed;
            __syncwarp();
            while (true) {
                int alive = __shfl_sync(0xffffffff, lane == 0 ? int(w.hp > 0) : 0, 0);
                if (!alive)
                    break;
                int key = -1;
                for (int i = lane; i < c.count; i += 32) {
                    int e = a.energy(i);
                    if (e >= 80)
                        key = mx(key, e * 128 + 127 - i);
                }
                for (int d = 16; d; d /= 2)
                    key = mx(key, __shfl_down_sync(0xffffffff, key, d));
                key = __shfl_sync(0xffffffff, key, 0);
                if (key < 0)
                    break;
                if (!lane)
                    act(w, a, c, m, 127 - (key & 127));
                __syncwarp();
            }
            if (!lane)
                finish(w, moves, attacks);
        }
        if (obs) {
            if (!lane) {
                obs[id * (c.count + 2)] = w.hp;
                obs[id * (c.count + 2) + 1] = w.blocks;
            }
            for (int i = lane; i < c.count; i += 32)
                obs[id * (c.count + 2) + i + 2] = visible(m, c.player, a.pos(i)) ? a.pos(i) : -1;
            __syncwarp();
        }
    }
    if (!lane)
        worlds[id] = w;
}
struct Fixture {
    Config c{};
    std::vector<uint8_t> floor;
    std::vector<uint16_t> dist;
    std::vector<uint32_t> los;
    std::vector<int16_t> starts;
    Fixture(const std::string &path) {
        std::ifstream f(path, std::ios::binary);
        if (!f)
            throw std::runtime_error("missing fixture: " + path);
        uint32_t magic;
        f.read((char *)&magic, 4);
        if (magic != 0x44314750)
            throw std::runtime_error("fixture format");
        int header[8];
        f.read((char *)header, sizeof(header));
        c.player = header[0];
        c.hp = header[1];
        c.ac100 = header[2];
        c.ev100 = header[3];
        c.sh100 = header[4];
        c.shield_limit = header[5];
        c.regen = header[6];
        c.repair = 1;
        for (int j = 0; j < 2; j++) {
            int ac = c.ac100 / 100 + j;
            int g = 0;
            while ((g + 1) * (g + 1) * (g + 1) * (g + 1) <= 65536 * ac)
                g++;
            c.gdr[j] = g;
        }
        f.read((char *)c.kinds, sizeof(c.kinds));
        floor.resize(N);
        dist.resize(N);
        los.resize(N * 10);
        starts.resize(2 * MAX);
        f.read((char *)floor.data(), N);
        f.read((char *)dist.data(), N * 2);
        f.read((char *)los.data(), N * 40);
        f.read((char *)starts.data(), MAX * 4);
        if (!f)
            throw std::runtime_error("truncated fixture");
    }
    Map map() { return {floor.data(), dist.data(), los.data(), starts.data()}; }
};
struct State {
    std::vector<World> w;
    std::vector<int16_t> pos, energy, occ, obs;
    int batch, count;
    bool tiled;
    State(int b, int n, bool t)
        : w(b), pos(b * n), energy(b * n), occ(size_t(b) * N, -1), obs(b * (n + 2)), batch(b),
          count(n), tiled(t) {}
    Access access() { return {pos.data(), energy.data(), occ.data(), 0, batch, count, tiled}; }
    void init(Config c, Map m, std::string scenario, uint64_t seed) {
        auto base = access();
        for (int id = 0; id < batch; id++) {
            Access a = base;
            a.world = id;
            World &v = w[id];
            v = {};
            v.rng.seed(mix(seed + id), id + 1);
            v.fixture = scenario == "approach" ? 1 : scenario == "mixed" ? id % 2 : 0;
            reset(v, a, c, m, true);
            if (scenario == "mixed")
                for (int k = 0; k < (id * 7) % 32; k++)
                    step<false>(v, a, c, m);
            v.s = {};
        }
    }
    void cpu(Config c, Map m, int steps, int threads, bool heap, bool observation) {
        auto base = access();
#pragma omp parallel for num_threads(threads) schedule(static)
        for (int id = 0; id < batch; id++) {
            auto a = base;
            a.world = id;
            World v = w[id];
            for (int k = 0; k < steps; k++) {
                if (heap)
                    step<true>(v, a, c, m);
                else
                    step<false>(v, a, c, m);
                if (observation)
                    observe(v, a, c, m, obs.data() + id * (count + 2));
            }
            w[id] = v;
        }
    }
    void validate(Config c, Map m) {
        auto base = access();
        for (int id = 0; id < batch; id++) {
            auto a = base;
            a.world = id;
            if (w[id].hp > c.hp || w[id].regen < 0 || w[id].regen >= 100)
                throw std::runtime_error("player invariant");
            int occupied = 0;
            for (int p = 0; p < N; p++)
                if (a.occ(p) >= 0) {
                    int i = a.occ(p);
                    if (i >= count || a.pos(i) != p)
                        throw std::runtime_error("occupancy bijection");
                    occupied++;
                }
            if (occupied != count)
                throw std::runtime_error("occupancy count");
            for (int i = 0; i < count; i++) {
                int p = a.pos(i);
                if (p < 0 || p >= N || !m.floor[p] || p == c.player || a.occ(p) != i)
                    throw std::runtime_error("position invariant");
            }
        }
    }
};
template <typename T> T *upload(const std::vector<T> &v) {
    T *p = nullptr;
    if (!v.empty()) {
        CUDA(cudaMalloc(&p, v.size() * sizeof(T)));
        CUDA(cudaMemcpy(p, v.data(), v.size() * sizeof(T), cudaMemcpyHostToDevice));
    }
    return p;
}
struct Device {
    World *w;
    Access a;
    Map m;
    int16_t *obs;
    size_t bytes;
    Device(State &s, Fixture &f) {
        w = upload(s.w);
        a = {upload(s.pos), upload(s.energy), upload(s.occ), 0, s.batch, s.count, s.tiled};
        m = {upload(f.floor), upload(f.dist), upload(f.los), upload(f.starts)};
        obs = upload(s.obs);
        bytes = s.w.size() * sizeof(World) +
                (s.pos.size() + s.energy.size() + s.occ.size() + s.obs.size()) * 2 + N * 43 +
                MAX * 4;
    }
    ~Device() {
        cudaFree(w);
        cudaFree(a.positions);
        cudaFree(a.energies);
        cudaFree(a.occupancy);
        cudaFree(obs);
        cudaFree((void *)m.floor);
        cudaFree((void *)m.dist);
        cudaFree((void *)m.los);
        cudaFree((void *)m.starts);
    }
    void restore(State &s) {
        CUDA(cudaMemcpy(w, s.w.data(), s.w.size() * sizeof(World), cudaMemcpyHostToDevice));
        if (s.count) {
            CUDA(cudaMemcpy(a.positions, s.pos.data(), s.pos.size() * 2, cudaMemcpyHostToDevice));
            CUDA(cudaMemcpy(a.energies, s.energy.data(), s.energy.size() * 2,
                            cudaMemcpyHostToDevice));
        }
        CUDA(cudaMemcpy(a.occupancy, s.occ.data(), s.occ.size() * 2, cudaMemcpyHostToDevice));
    }
    void run(Config c, int steps, bool warp, bool heap, bool observation) {
        int threads = 128, blocks = (a.batch * (warp ? 32 : 1) + threads - 1) / threads;
        int16_t *o = observation ? obs : nullptr;
        if (warp) {
            if (heap)
                warp_run<true><<<blocks, threads>>>(w, a, c, m, steps, o);
            else
                warp_run<false><<<blocks, threads>>>(w, a, c, m, steps, o);
        } else {
            if (heap)
                thread_run<true><<<blocks, threads>>>(w, a, c, m, steps, o);
            else
                thread_run<false><<<blocks, threads>>>(w, a, c, m, steps, o);
        }
        CUDA(cudaGetLastError());
    }
    void download(State &s, bool all = true) {
        CUDA(cudaMemcpy(s.w.data(), w, s.w.size() * sizeof(World), cudaMemcpyDeviceToHost));
        if (all) {
            if (s.count) {
                CUDA(cudaMemcpy(s.pos.data(), a.positions, s.pos.size() * 2,
                                cudaMemcpyDeviceToHost));
                CUDA(cudaMemcpy(s.energy.data(), a.energies, s.energy.size() * 2,
                                cudaMemcpyDeviceToHost));
            }
            CUDA(cudaMemcpy(s.occ.data(), a.occupancy, s.occ.size() * 2, cudaMemcpyDeviceToHost));
            CUDA(cudaMemcpy(s.obs.data(), obs, s.obs.size() * 2, cudaMemcpyDeviceToHost));
        }
    }
};
static void compare(State &a, State &b, bool observation) {
    auto aa = a.access(), bb = b.access();
    for (int i = 0; i < a.batch; i++) {
        World &x = a.w[i];
        World &y = b.w[i];
        if (x.hp != y.hp || x.regen != y.regen || x.blocks != y.blocks || x.episode != y.episode ||
            x.rng.state != y.rng.state || x.rng.inc != y.rng.inc ||
            memcmp(&x.s, &y.s, sizeof(Stats)))
            throw std::runtime_error("CPU/GPU world mismatch at " + std::to_string(i));
        aa.world = bb.world = i;
        for (int j = 0; j < a.count; j++)
            if (aa.pos(j) != bb.pos(j) || aa.energy(j) != bb.energy(j))
                throw std::runtime_error("actor mismatch");
    }
    if (observation && a.obs != b.obs)
        throw std::runtime_error("observation mismatch");
}
static void selftest(Fixture &f) {
    for (int n : {0, 1, 8, 32, 64})
        for (bool heap : {false, true}) {
            auto c = f.c;
            c.count = n;
            auto m = f.map();
            State cpu(37, n, false);
            cpu.init(c, m, "mixed", 42);
            cpu.cpu(c, m, 257, 1, heap, true);
            cpu.validate(c, m);
            for (bool warp : {false, true}) {
                State gpu(37, n, warp);
                gpu.init(c, m, "mixed", 42);
                Device d(gpu, f);
                d.run(c, 257, warp, heap, true);
                CUDA(cudaDeviceSynchronize());
                d.download(gpu);
                gpu.validate(c, m);
                compare(cpu, gpu, true);
            }
        }

    // Chunk boundaries must not alter trajectories or observations.
    {
        auto c = f.c;
        c.count = 8;
        State ref(37, 8, false);
        ref.init(c, f.map(), "mixed", 999);
        ref.cpu(c, f.map(), 257, 1, false, true);
        for (bool warp : {false, true}) {
            State v(37, 8, warp);
            v.init(c, f.map(), "mixed", 999);
            Device d(v, f);
            for (int done = 0; done < 257; done += 17)
                d.run(c, std::min(17, 257 - done), warp, false, true);
            CUDA(cudaDeviceSynchronize());
            d.download(v);
            v.validate(c, f.map());
            compare(ref, v, true);
        }
    }
    // With no deaths, energy gained minus energy remaining accounts for every action.
    {
        auto c = f.c;
        c.count = 6;
        c.hp = 1000000;
        State v(1, 6, true);
        v.init(c, f.map(), "combat", 73);
        int initial = 0, gain = 0;
        for (int i = 0; i < 6; i++) {
            initial += v.energy[i];
            gain += c.kinds[i].speed;
        }
        v.cpu(c, f.map(), 1000, 1, false, false);
        int final = 0;
        for (int e : v.energy) {
            if (e < 70 || e >= 80)
                throw std::runtime_error("energy range");
            final += e;
        }
        if (v.w[0].s.deaths || initial + 1000 * gain - final != 10 * int(v.w[0].s.actions))
            throw std::runtime_error("energy accounting");
    }
    // Both stable-tie schedulers must produce identical trajectories.
    auto c = f.c;
    c.count = 64;
    State a(37, 64, false), b(37, 64, false);
    a.init(c, f.map(), "mixed", 17);
    b.init(c, f.map(), "mixed", 17);
    a.cpu(c, f.map(), 400, 1, false, true);
    b.cpu(c, f.map(), 400, 1, true, true);
    compare(a, b, true);
    printf("{\"selftest\":\"passed\",\"worlds_per_case\":37,\"steps\":257,\"counts\":[0,1,8,32,64],"
           "\"gpu_layouts\":2,\"schedulers\":2,\"checks\":\"exact RNG/state/counters/observations; "
           "occupancy; heap-scan parity\"}\n");
}
int main(int argc, char **argv) {
    try {
        std::string fixture = "gpu-d1/fixtures/fixture.bin", backend = "thread", scenario = "mixed";
        int batch = 4096, count = 16, steps = 256, chunk = 64, trials = 3, threads = 1;
        bool heap = false, obs = false, test = false, oracle = false, lifecheck = false;
        uint64_t seed = 42;
        for (int i = 1; i < argc; i++) {
            std::string k = argv[i];
            auto value = [&]() {
                if (i + 1 >= argc)
                    throw std::runtime_error("missing option value");
                return std::string(argv[++i]);
            };
            if (k == "--fixture")
                fixture = value();
            else if (k == "--backend")
                backend = value();
            else if (k == "--scenario")
                scenario = value();
            else if (k == "--batch")
                batch = std::stoi(value());
            else if (k == "--monsters")
                count = std::stoi(value());
            else if (k == "--steps")
                steps = std::stoi(value());
            else if (k == "--chunk")
                chunk = std::stoi(value());
            else if (k == "--trials")
                trials = std::stoi(value());
            else if (k == "--threads")
                threads = std::stoi(value());
            else if (k == "--seed")
                seed = std::stoull(value());
            else if (k == "--heap")
                heap = true;
            else if (k == "--observe")
                obs = true;
            else if (k == "--selftest")
                test = true;
            else if (k == "--combat-check")
                oracle = true;
            else if (k == "--lifetimes")
                lifecheck = true;
            else
                throw std::runtime_error("unknown option " + k);
        }
        if (batch < 1 || batch > 131072 || count < 0 || count > MAX || steps < 1 || chunk < 1 ||
            trials < 1 || threads < 1)
            throw std::runtime_error("argument out of bounds");
        if (backend != "cpu" && backend != "thread" && backend != "warp")
            throw std::runtime_error("invalid backend");
        if (scenario != "quiet" && scenario != "approach" && scenario != "combat" &&
            scenario != "mixed")
            throw std::runtime_error("invalid scenario");
        auto load_start = std::chrono::steady_clock::now();
        Fixture f(fixture);
        double load_seconds =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - load_start).count();
        if (test) {
            selftest(f);
            return 0;
        }
        if (oracle) {
            for (int id = 0; id < 6; id++)
                for (int pre = 0; pre <= 2; pre++) {
                    World w{};
                    w.rng.seed(mix(seed + id * 3 + pre), id * 3 + pre + 1);
                    for (int k = 0; k < steps; k++) {
                        w.hp = f.c.hp;
                        w.blocks = pre;
                        attack(w, f.c, id);
                    }
                    printf(
                        "{\"backend\":\"compact-oracle\",\"kind\":%d,\"preblocks\":%d,\"samples\":%"
                        "d,\"attacks\":%llu,\"blocks\":%llu,\"dodges\":%llu,\"damage\":%llu}\n",
                        id, pre, steps, (unsigned long long)w.s.attacks,
                        (unsigned long long)w.s.blocks, (unsigned long long)w.s.dodges,
                        (unsigned long long)w.s.damage);
                }
            return 0;
        }
        if (scenario == "quiet")
            count = 0;
        auto c = f.c;
        c.count = count;
        bool gpu = backend != "cpu", warp = backend == "warp";
        if (lifecheck) {
            State v(1, count, true);
            v.init(c, f.map(), scenario, seed);
            auto a = v.access();
            std::vector<int> lives;
            int life = 0;
            for (int k = 0; k < steps; k++) {
                step<false>(v.w[0], a, c, f.map());
                life++;
                if (v.w[0].hp <= 0) {
                    lives.push_back(life);
                    life = 0;
                }
            }
            v.validate(c, f.map());
            std::sort(lives.begin(), lives.end());
            double sum = 0;
            for (int x : lives)
                sum += x;
            auto &z = v.w[0].s;
            printf("{\"backend\":\"compact-lifetimes\",\"scenario\":\"%s\",\"monsters\":%d,"
                   "\"episodes\":%zu,\"mean\":%.6f,\"p10\":%d,\"p50\":%d,\"p90\":%d,\"turns\":%llu,"
                   "\"actions\":%llu,\"attacks\":%llu,\"damage\":%llu}\n",
                   scenario.c_str(), count, lives.size(), lives.empty() ? 0 : sum / lives.size(),
                   lives.empty() ? 0 : lives[lives.size() / 10],
                   lives.empty() ? 0 : lives[lives.size() / 2],
                   lives.empty() ? 0 : lives[lives.size() * 9 / 10], (unsigned long long)z.turns,
                   (unsigned long long)z.actions, (unsigned long long)z.attacks,
                   (unsigned long long)z.damage);
            return 0;
        }
        auto init_start = std::chrono::steady_clock::now();
        State state(batch, count, gpu ? warp : true);
        state.init(c, f.map(), scenario, seed);
        double init_seconds =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - init_start).count();
        auto upload_start = std::chrono::steady_clock::now();
        Device *device = gpu ? new Device(state, f) : nullptr;
        double upload_seconds =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - upload_start).count();
        auto warm_start = std::chrono::steady_clock::now();
        if (gpu) {
            device->run(c, 32, warp, heap, obs);
            CUDA(cudaDeviceSynchronize());
            device->restore(state);
        } else {
            State warm = state;
            warm.cpu(c, f.map(), 32, threads, heap, obs);
        }
        double warm_seconds =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - warm_start).count();
        for (int t = 0; t < trials; t++) {
            if (t) {
                state = State(batch, count, gpu ? warp : true);
                state.init(c, f.map(), scenario, seed);
                if (gpu)
                    device->restore(state);
            }
            cudaEvent_t start = nullptr, stop = nullptr;
            if (gpu) {
                CUDA(cudaEventCreate(&start));
                CUDA(cudaEventCreate(&stop));
                CUDA(cudaDeviceSynchronize());
            }
            auto before = std::chrono::steady_clock::now();
            if (gpu)
                CUDA(cudaEventRecord(start));
            for (int done = 0; done < steps; done += chunk) {
                int k = std::min(chunk, steps - done);
                if (gpu)
                    device->run(c, k, warp, heap, obs);
                else
                    state.cpu(c, f.map(), k, threads, heap, obs);
            }
            float ms = 0;
            if (gpu) {
                CUDA(cudaEventRecord(stop));
                CUDA(cudaEventSynchronize(stop));
                CUDA(cudaEventElapsedTime(&ms, start, stop));
            }
            double wall =
                std::chrono::duration<double>(std::chrono::steady_clock::now() - before).count();
            auto download_start = std::chrono::steady_clock::now();
            if (gpu) {
                device->download(state);
                CUDA(cudaEventDestroy(start));
                CUDA(cudaEventDestroy(stop));
            }
            double download_seconds =
                std::chrono::duration<double>(std::chrono::steady_clock::now() - download_start)
                    .count();
            state.validate(c, f.map());
            Stats totals{};
            uint64_t checksum = 0;
            for (auto &w : state.w) {
                totals.turns += w.s.turns;
                totals.actions += w.s.actions;
                totals.attacks += w.s.attacks;
                totals.blocks += w.s.blocks;
                totals.dodges += w.s.dodges;
                totals.damage += w.s.damage;
                totals.deaths += w.s.deaths;
                totals.resets += w.s.resets;
                totals.moves += w.s.moves;
                totals.repairs += w.s.repairs;
                totals.stalls += w.s.stalls;
                totals.move_turns += w.s.move_turns;
                totals.combat_turns += w.s.combat_turns;
                checksum ^= mix(w.rng.state + uint64_t(w.hp));
            }
            for (auto x : state.pos)
                checksum = mix(checksum + uint16_t(x));
            if (obs)
                for (auto x : state.obs)
                    checksum = mix(checksum + uint16_t(x));
            if (totals.turns != uint64_t(batch) * steps)
                throw std::runtime_error("turn accounting");
            printf("{\"fixture_load_s\":%.6f,\"state_init_s\":%.6f,\"device_setup_s\":%.6f,"
                   "\"warmup_s\":%.6f,\"final_readback_s\":%.6f,",
                   load_seconds, init_seconds, upload_seconds, warm_seconds, download_seconds);
            printf("\"backend\":\"%s\",\"threads\":%d,\"scheduler\":\"%s\",\"scenario\":\"%s\","
                   "\"batch\":%d,\"monsters\":%d,\"steps\":%d,\"chunk\":%d,\"observe\":%s,"
                   "\"trial\":%d,\"wall_s\":%.9f,\"gpu_ms\":%.6f,\"waits_per_s\":%.3f,\"turns\":%"
                   "llu,\"actions\":%llu,\"attacks\":%llu,\"blocks\":%llu,\"dodges\":%llu,"
                   "\"damage\":%llu,\"deaths\":%llu,\"resets\":%llu,\"moves\":%llu,\"repairs\":%"
                   "llu,\"stalls\":%llu,\"move_turns\":%llu,\"combat_turns\":%llu,\"device_bytes\":"
                   "%zu,\"checksum\":\"%016llx\"}\n",
                   backend.c_str(), threads, heap ? "heap" : "scan", scenario.c_str(), batch, count,
                   steps, chunk, obs ? "true" : "false", t, wall, ms, totals.turns / wall,
                   (unsigned long long)totals.turns, (unsigned long long)totals.actions,
                   (unsigned long long)totals.attacks, (unsigned long long)totals.blocks,
                   (unsigned long long)totals.dodges, (unsigned long long)totals.damage,
                   (unsigned long long)totals.deaths, (unsigned long long)totals.resets,
                   (unsigned long long)totals.moves, (unsigned long long)totals.repairs,
                   (unsigned long long)totals.stalls, (unsigned long long)totals.move_turns,
                   (unsigned long long)totals.combat_turns, gpu ? device->bytes : 0,
                   (unsigned long long)checksum);
            fflush(stdout);
        }
        delete device;
        return 0;
    } catch (const std::exception &e) {
        fprintf(stderr, "ERROR: %s\n", e.what());
        return 1;
    }
}
