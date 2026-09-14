// Compiled only into the isolated native l-debug.cc translation unit.
#include "newgame-def.h"
#include "env.h"
#include "package.h"
#include "terrain.h"
#include "mon-util.h"
#include "item-name.h"
#include "fight.h"
#include "player.h"
#include "initfile.h"
#include <fstream>
extern void gpu_export_rays(const char *path);
LUAFN(gpu_export) {
    const string root = luaL_checkstring(ls, 1);
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
        return luaL_error(ls, "native builder failed");
    FILE *f = fopen((root + ".json").c_str(), "w");
    if (!f)
        return luaL_error(ls, "cannot open export");
    fprintf(
        f,
        "{\"seed\":%llu,\"width\":80,\"height\":70,\"hp\":%d,\"ac100\":%d,\"ev100\":%d,\"sh100\":%"
        "d,\"shield_limit\":%d,\"regen\":%d,\"str\":%d,\"dex\":%d,\"int\":%d,\"terrain\":[",
        (unsigned long long)crawl_state.seed, you.hp_max, you.armour_class_scaled(100),
        you.evasion_scaled(100), player_shield_class(100, false), you.shield_block_limit(),
        player_regen(), you.strength(), you.dex(), you.intel());
    for (int y = 0; y < GYM; y++)
        for (int x = 0; x < GXM; x++)
            fprintf(f, "%s%d", (x || y) ? "," : "", (int)env.grid(coord_def(x, y)));
    fprintf(f, "],\"map\":[");
    int unsupported = 0;
    for (int y = 0; y < GYM; y++) {
        fprintf(f, "%s\"", y ? "," : "");
        for (int x = 0; x < GXM; x++) {
            const auto ft = env.grid(coord_def(x, y));
            char c = '?';
            if (ft == DNGN_FLOOR)
                c = '.';
            else if (ft == DNGN_ROCK_WALL || ft == DNGN_STONE_WALL || ft == DNGN_PERMAROCK_WALL)
                c = '#';
            else if (feat_is_staircase(ft) || ft == DNGN_EXIT_DUNGEON)
                c = '.';
            if (c == '?')
                unsupported++;
            fputc(c, f);
        }
        fputc('"', f);
    }
    fprintf(f, "],\"unsupported_tiles\":%d,\"native_monsters\":[", unsupported);
    int n = 0;
    for (monster_iterator mi; mi; ++mi) {
        auto &m = **mi;
        fprintf(f, "%s{\"type\":%d,\"x\":%d,\"y\":%d,\"hp\":%d,\"speed\":%d,\"energy\":%d}",
                n++ ? "," : "", (int)m.type, m.pos().x, m.pos().y, m.hit_points, m.speed,
                m.speed_increment);
    }
    fprintf(f, "],\"native_items\":[");
    n = 0;
    for (int i = 0; i < MAX_ITEMS; i++)
        if (env.item[i].defined()) {
            const auto &it = env.item[i];
            fprintf(f,
                    "%s{\"base\":%d,\"subtype\":%d,\"plus\":%d,\"brand\":%d,\"quantity\":%d,\"x\":%"
                    "d,\"y\":%d}",
                    n++ ? "," : "", (int)it.base_type, it.sub_type, it.plus, it.brand, it.quantity,
                    it.pos.x, it.pos.y);
        }
    fprintf(f, "],\"player_items\":[");
    n = 0;
    for (int i = 0; i < ENDOFPACK; i++)
        if (you.inv[i].defined()) {
            const auto &it = you.inv[i];
            fprintf(f,
                    "%s{\"slot\":%d,\"name\":\"%s\",\"base\":%d,\"subtype\":%d,\"plus\":%d,"
                    "\"brand\":%d,\"quantity\":%d}",
                    n++ ? "," : "", i, it.name(DESC_PLAIN).c_str(), (int)it.base_type, it.sub_type,
                    it.plus, it.brand, it.quantity);
        }
    fprintf(f, "],\"map_marker_count\":%zu,\"roster\":[", env.markers.get_all().size());
    const monster_type kinds[] = {MONS_RAT,       MONS_FRILLED_LIZARD, MONS_GOBLIN,
                                  MONS_HOBGOBLIN, MONS_QUOKKA,         MONS_JACKAL};
    for (int i = 0; i < 6; i++) {
        const auto *m = get_monster_data(kinds[i]);
        fprintf(f,
                "%s{\"name\":\"%s\",\"native_type\":%d,\"hd\":%d,\"damage\":%d,\"speed\":%d,\"to_"
                "hit\":%d,\"bypass\":%d}",
                i ? "," : "", m->name, (int)kinds[i], m->HD, m->attack[0].damage, m->speed,
                mon_to_hit_base(m->HD, false), mon_shield_bypass(m->HD));
    }
    fprintf(f, "]}\n");
    fclose(f);
    FILE *markers = fopen((root + ".markers").c_str(), "w");
    for (auto *marker : env.markers.get_all())
        fprintf(markers, "%d %d %d %s\n", int(marker->get_type()), marker->pos.x,
                marker->pos.y, marker->debug_describe().c_str());
    fclose(markers);
    if (!unsupported) {
        FILE *out = fopen((root + ".los").c_str(), "wb");
        for (int y = 0; y < GYM; y++)
            for (int x = 0; x < GXM; x++) {
                los_grid grid;
                losight(grid, coord_def(x, y), opc_fullyopaque);
                for (int dy = -8; dy <= 8; dy++)
                    for (int dx = -8; dx <= 8; dx++)
                        fputc(grid(coord_def(dx, dy)) ? 1 : 0, out);
            }
        fclose(out);
        gpu_export_rays((root + ".rays").c_str());
    }
    printf("exported %s seed=%llu unsupported=%d hp=%d\n", root.c_str(),
           (unsigned long long)crawl_state.seed, unsupported, you.hp_max);
    delete you.save;
    you.save = nullptr;
    return 0;
}
