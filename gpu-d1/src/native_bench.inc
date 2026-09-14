#include "areas.h"
#include "losglobal.h"
#include "native_hooks.h"
#include "melee-attack.h"
#include "mon-place.h"
#include "mgen-data.h"
#include "random.h"
#include <chrono>

bool gpu_d1_active = false;
GpuNativeStats gpu_d1_stats{};

// Calls native implementations, not the compact formulas, for the oracle.
struct gpu_native_access {
    static void sample(monster &m) {
        melee_attack a(&m, &you);
        a.init_attack(0);
        const int margin = a.test_hit(a.to_hit, you.evasion(false, &m), true);
        gpu_d1_stats.attacks++;
        if (a.attack_shield_blocked()) {
            you.shield_block_succeeded(&m);
            gpu_d1_stats.blocks++;
        } else if (margin < 0)
            gpu_d1_stats.dodges++;
        else {
            int damage = a.calc_damage();
            gpu_d1_stats.damage += damage;
            you.hp -= damage;
        }
    }
};

LUAFN(gpu_bench) {
    const string path = luaL_checkstring(ls, 1);
    const int count = luaL_checkinteger(ls, 2), steps = luaL_checkinteger(ls, 3);
    const string mode = luaL_checkstring(ls, 4);
    if (count < 0 || count > 64 || steps < 1)
        return luaL_error(ls, "bad dimensions");
    std::ifstream f(path, std::ios::binary);
    uint32_t magic;
    int h[8];
    f.read((char *)&magic, 4);
    f.read((char *)h, sizeof(h));
    if (!f || magic != 0x44314750)
        return luaL_error(ls, "bad fixture");
    f.seekg(6 * 16, std::ios::cur);
    unsigned char floor[5600];
    f.read((char *)floor, 5600);
    f.seekg(5600 * 42, std::ios::cur);
    int16_t starts[128];
    f.read((char *)starts, sizeof(starts));
    if (!f)
        return luaL_error(ls, "short fixture");
    newgame_def ng;
    ng.name = "GPUHuman";
    ng.type = GAME_TYPE_CUSTOM_SEED;
    ng.species = SP_HUMAN;
    ng.job = JOB_FIGHTER;
    ng.weapon = WPN_LONG_SWORD;
    Options.no_save = true;
    setup_game(ng, true);
    you.where_are_you = BRANCH_DUNGEON;
    you.depth = 1;
    if (!builder(true))
        return luaL_error(ls, "builder failed");
    for (int i = 0; i < MAX_MONSTERS; i++)
        env.mons[i].reset();
    env.mid_cache.clear();
    for (int p = 0; p < 5600; p++) {
        env.grid(coord_def(p % 80, p / 80)) = floor[p] ? DNGN_FLOOR : DNGN_ROCK_WALL;
        env.mgrid(coord_def(p % 80, p / 80)) = NON_MONSTER;
    }
    you.move_to(coord_def(h[0] % 80, h[0] / 80));
    invalidate_los();
    invalidate_agrid(true);
    const monster_type kinds[] = {MONS_RAT,       MONS_FRILLED_LIZARD, MONS_GOBLIN,
                                  MONS_HOBGOBLIN, MONS_QUOKKA,         MONS_JACKAL};
    vector<monster *> mons;
    vector<monster> templates;
    const int offset = mode == "approach" ? 64 : 0;
    for (int i = 0; i < count; i++) {
        const int p = starts[offset + i];
        monster *m = place_monster(
            mgen_data(kinds[i % 6], BEH_HOSTILE, coord_def(p % 80, p / 80), MHITYOU), true);
        if (!m)
            return luaL_error(ls, "monster placement failed");
        m->inv.init(NON_ITEM);
        m->spells.clear();
        m->behaviour = BEH_SEEK;
        m->target = you.pos();
        m->foe_memory = 1000;
        m->flags &= ~MF_JUST_SUMMONED;
        m->speed_increment = 70 + random2(10);
        mons.push_back(m);
        templates.push_back(*m);
    }
    for (int i = 0; i < MAX_ITEMS; i++)
        env.item[i].clear();
    env.igrid.init(NON_ITEM);
    gpu_d1_active = true;
    if (mode == "oracle") {
        if (count != 6)
            return luaL_error(ls, "oracle requires six monsters");
        for (int i = 0; i < 6; i++)
            for (int pre = 0; pre <= 2; pre++) {
                gpu_d1_stats = {};
                for (int k = 0; k < steps; k++) {
                    you.hp = h[1];
                    you.shield_blocks = pre;
                    gpu_native_access::sample(*mons[i]);
                }
                printf("{\"backend\":\"native-oracle\",\"kind\":%d,\"preblocks\":%d,\"samples\":%d,"
                       "\"attacks\":%llu,\"blocks\":%llu,\"dodges\":%llu,\"damage\":%llu}\n",
                       i, pre, steps, (unsigned long long)gpu_d1_stats.attacks,
                       (unsigned long long)gpu_d1_stats.blocks,
                       (unsigned long long)gpu_d1_stats.dodges,
                       (unsigned long long)gpu_d1_stats.damage);
            }
    } else {
        vector<int> lives;
        lives.reserve(steps);
        int life = 0;
        auto reset = [&](bool first) {
            gpu_native_clear_queue();
            for (auto *m : mons)
                env.mgrid(m->pos()) = NON_MONSTER;
            for (int i = 0; i < count; i++) {
                *mons[i] = templates[i];
                mons[i]->speed_increment = 70 + random2(10);
                env.mgrid(mons[i]->pos()) = mons[i]->mindex();
            }
            you.hp = h[1];
            you.hit_points_regeneration = 0;
            you.shield_blocks = 0;
            if (!first)
                gpu_d1_stats.resets++;
        };
        auto run = [&](int turns) {
            for (int k = 0; k < turns; k++) {
                if (you.hp <= 0)
                    reset(false);
                you.shield_blocks = 0;
                you.time_taken = 10;
                you.turn_is_over = true;
                you.hit_points_regeneration += player_regen();
                while (you.hit_points_regeneration >= 100) {
                    you.hp = min(you.hp_max, you.hp + 1);
                    you.hit_points_regeneration -= 100;
                }
                uint64_t moves = gpu_d1_stats.moves, attacks = gpu_d1_stats.attacks;
                gpu_d1_stats.turns++;
                life++;
                try {
                    handle_monsters(false);
                } catch (const gpu_d1_terminal &) {
                    gpu_d1_stats.deaths++;
                    gpu_native_clear_queue();
                    lives.push_back(life);
                    life = 0;
                }
                gpu_d1_stats.move_turns += (moves != gpu_d1_stats.moves);
                gpu_d1_stats.combat_turns += (attacks != gpu_d1_stats.attacks);
                crawl_state.clear_mon_acting();
            }
        };
        run(128);
        reset(true);
        gpu_d1_stats = {};
        lives.clear();
        life = 0;
        auto before = std::chrono::steady_clock::now();
        run(steps);
        double wall =
            std::chrono::duration<double>(std::chrono::steady_clock::now() - before).count();
        auto &s = gpu_d1_stats;
        sort(lives.begin(), lives.end());
        double life_sum = 0;
        for (int x : lives)
            life_sum += x;
        printf("{\"backend\":\"native-lifetimes\",\"scenario\":\"%s\",\"monsters\":%d,\"episodes\":"
               "%zu,\"mean\":%.6f,\"p10\":%d,\"p50\":%d,\"p90\":%d}\n",
               mode.c_str(), count, lives.size(), lives.empty() ? 0 : life_sum / lives.size(),
               lives.empty() ? 0 : lives[lives.size() / 10],
               lives.empty() ? 0 : lives[lives.size() / 2],
               lives.empty() ? 0 : lives[lives.size() * 9 / 10]);
        printf("{\"backend\":\"native-reference\",\"scenario\":\"%s\",\"monsters\":%d,\"wall_s\":%."
               "9f,\"waits_per_s\":%.3f,\"turns\":%llu,\"actions\":%llu,\"attacks\":%llu,"
               "\"blocks\":%llu,\"dodges\":%llu,\"damage\":%llu,\"deaths\":%llu,\"resets\":%llu,"
               "\"moves\":%llu,\"move_turns\":%llu,\"combat_turns\":%llu}\n",
               mode.c_str(), count, wall, s.turns / wall, (unsigned long long)s.turns,
               (unsigned long long)s.actions, (unsigned long long)s.attacks,
               (unsigned long long)s.blocks, (unsigned long long)s.dodges,
               (unsigned long long)s.damage, (unsigned long long)s.deaths,
               (unsigned long long)s.resets, (unsigned long long)s.moves,
               (unsigned long long)s.move_turns, (unsigned long long)s.combat_turns);
    }
    gpu_d1_active = false;
    gpu_native_clear_queue();
    delete you.save;
    you.save = nullptr;
    return 0;
}
