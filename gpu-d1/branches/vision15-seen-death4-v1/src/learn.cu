// Minimal floor-clear proxy task. Shared incoming combat: sim.h (GPL-2.0-or-later).
// Player attacks and monster HP below are explicit proxy rules, not native melee.
#include "sim.h"
#include <cuda_runtime.h>
#include <cassert>
#include <cstring>
using namespace sim;
// The vision screen supports only the audited route/memory observation schema.
// Legacy healing has a smaller OUT buffer; raw awake slots bypass visibility.
#if defined(HEAL_CHARGES) || defined(MONSTER_AWAKE_OBS)
#error Vision v1 does not support healing or raw awake-status channels; integrate visibility and buffer layouts first
#endif
#if !defined(MULTI_MAP) || !defined(SLEEP_ON) || !defined(EXPLORE_REWARD) || !defined(MARK_WALLS) || !defined(KNOWN_FRONTIER) || !defined(FRONTIER_RING_MEMORY_WALLS_OBS) || !defined(FRONTIER_ROUTE_CUE_OBS)
#error Vision v1 requires the audited multi-map sleep/remembered-ring/frontier-route build
#endif
#if defined(SPATIAL_MAP_OBS) || defined(FULL_MAP_OBS) || defined(FRONTIER_RING12_OBS) || defined(SEEN_OBS)
#error Legacy observation overrides are not integrated with the vision v1 schema
#endif
namespace learn {
#ifndef FRONTIER_TRAVEL
#define FRONTIER_TRAVEL 0
#endif

#ifndef OGRE_COUNT
#define OGRE_COUNT 0
#endif
#ifndef OPTIONAL_LABEL_OBS
#define OPTIONAL_LABEL_OBS 0
#endif
#ifndef OGRE_FEATURES
#define OGRE_FEATURES 0
#endif
static_assert(OGRE_COUNT>=0 && OGRE_COUNT<=2);
static_assert(OGRE_FEATURES==0 && OPTIONAL_LABEL_OBS==0, "Only the local baseline observation is integrated");
// Feature bits: awake=1, speed=2, stats=4, next-action readiness=8.
constexpr int REQUIRED=24;
#if defined(HEAL_CHARGES) || defined(MONSTER_AWAKE_OBS)
#error Use OGRE_FEATURES; healing is not part of this branch
#endif
HD Kind monster_kind(const Config &c, int id) {
    return id>=REQUIRED ? Kind{5,24,30,25} : c.kinds[id%6];
}


#ifndef MONSTER_WAKE_LOS
#define MONSTER_WAKE_LOS 1
#endif

// Keep direct/legacy builds of the route task on the same fast defaults.
// Reference benchmarks explicitly opt out; other observation tasks keep 128.
#if defined(FRONTIER_ROUTE_CUE_OBS) && defined(KNOWN_FRONTIER) && !defined(REFERENCE_PERFORMANCE)
#ifndef FAST_FRONTIER
#define FAST_FRONTIER
#endif
#ifndef LEARN_BLOCK_SIZE
#define LEARN_BLOCK_SIZE 4
#endif
#endif
#ifndef LEARN_BLOCK_SIZE
#define LEARN_BLOCK_SIZE 128
#endif
constexpr int BLOCK_SIZE=LEARN_BLOCK_SIZE;
#ifndef TERRAIN_LOS
#define TERRAIN_LOS 1
#endif
#ifndef GLOBAL_ENEMIES
#define GLOBAL_ENEMIES 0
#endif
#ifdef HEAL_CHARGES
static_assert(HEAL_CHARGES >= 0 && HEAL_CHARGES <= 7);
#if !defined(FRONTIER_ROUTE_CUE_OBS) || !defined(EXPLORE_REWARD)
#error Healing requires the corrected route and exploration-reward build
#endif
constexpr int ACTIONS=10, OUT=12;
#else
constexpr int ACTIONS=9+FRONTIER_TRAVEL, OUT=34;
#endif
#ifndef EXPLORE_MILLI
#define EXPLORE_MILLI 2
#endif
#ifndef KILL_MILLI
#define KILL_MILLI 1000
#endif
#ifndef CLEAR_MILLI
#define CLEAR_MILLI 3000
#endif
#ifndef DEATH_MILLI
#define DEATH_MILLI 1000
#endif
#ifndef CLEAR_PER_ENEMY_MILLI
#define CLEAR_PER_ENEMY_MILLI 0
#endif
#ifdef LEARN_ENEMIES
constexpr int ENEMIES = LEARN_ENEMIES;
#else
constexpr int ENEMIES = 8;
#endif
constexpr int VIEW_RADIUS=7, SIDE=2*VIEW_RADIUS+1, VIEW_CELLS=SIDE*SIDE;
constexpr int RING_RADIUS=VIEW_RADIUS+1, RING_CELLS=8*RING_RADIUS;
constexpr int PLAYER_OBS=VIEW_CELLS*2+ENEMIES*5, BASE_OBS=PLAYER_OBS+4;
constexpr int FRONTIER_OBS=BASE_OBS+RING_CELLS;
#ifndef PROGRESS_INPUT
#define PROGRESS_INPUT 0
#endif
constexpr int ORIGINAL_OBS=FRONTIER_OBS+7+8+VIEW_CELLS;
constexpr int OBS=ORIGINAL_OBS+1;
static_assert(VIEW_RADIUS<=8 && ORIGINAL_OBS==958 && OBS==959);
struct State {
    int ogres_killed, ogre_damage, ogre_actions, ogre_adjacent_turns, ogre_fatal;
#ifdef HEAL_CHARGES
    int charges, heals_used, heal_hp_sum, restored_hp_sum;
#endif
    World w;
    int player, ticks, killed;
    int map_id;
    int next_slot, floor_seen;
    int16_t enemy_slot[ENEMIES];
    uint8_t encountered[ENEMIES];
    int16_t pos[ENEMIES], energy[ENEMIES], occ[N], hp[ENEMIES];
#ifdef SLEEP_ON
    int16_t awake[ENEMIES];
#endif
#ifdef EXPLORE_REWARD
    uint8_t seen[N];
#ifdef MARK_WALLS
    uint8_t viewed[N];
#endif
#if defined(FRONTIER_MEMORY_OBS) || defined(FRONTIER_MEMORY_WALLS_OBS) || defined(FRONTIER_RING_MEMORY_WALLS_OBS)
    // Active frontier anchors are maintained incrementally as seen cells are
    // added, avoiding a full-map scan for every observation.
    int16_t frontier_cells[N], frontier_slot[N];
    int frontier_count;
#endif
#endif
};
struct Tables {
    const uint8_t *floor;
    const int16_t *cells, *index;
    const uint16_t *distance;
    int ncells;
#ifdef MULTI_MAP
    const int *map_ncells, *distance_offsets;
    int n_maps, map_filter;
    const uint32_t *los;
#endif
};
HD Access access(State &s, int count) { return {s.pos, s.energy, s.occ, 0, 1, count, true}; }
HD const uint8_t *floor_map(const Tables &t, int map_id) {
#ifdef MULTI_MAP
    return t.floor + map_id*N;
#else
    (void)map_id;
    return t.floor;
#endif
}
HD bool floor_at(const Tables &t, int map_id, int p) {
    return p >= 0 && p < N && floor_map(t, map_id)[p];
}
HD const int16_t *cells_map(const Tables &t, int map_id) {
#ifdef MULTI_MAP
    return t.cells + map_id*N;
#else
    (void)map_id;
    return t.cells;
#endif
}
HD int cell_count(const Tables &t, int map_id) {
#ifdef MULTI_MAP
    return t.map_ncells[map_id];
#else
    (void)map_id;
    return t.ncells;
#endif
}
HD const uint16_t *field(const Tables &t, int map_id, int player) {
#ifdef MULTI_MAP
    int16_t row = t.index[map_id*N + player];
    return t.distance + (size_t(t.distance_offsets[map_id]) + size_t(row))*N;
#else
    (void)map_id;
    return t.distance + int(t.index[player])*N;
#endif
}
// Static native-exported LOS, cropped to the 15x15 sensor range.
HD bool in_view(const State &s, const Tables &t, int target) {
    int dx=target%W-s.player%W, dy=target/W-s.player/W;
    if(target<0 || target>=N || abs(dx)>VIEW_RADIUS || abs(dy)>VIEW_RADIUS) return false;
    if(!TERRAIN_LOS) return true;
    int bit=(dy+8)*17+dx+8;
    return (t.los[(size_t(s.map_id)*N+s.player)*10+bit/32]>>(bit%32))&1;
}
// Monster detection uses its own LOS origin and the original six-tile range.
// This gates waking only; awake monsters retain the existing pursuit behavior.
HD bool monster_detects_player(const State &s, const Tables &t, int origin) {
    int dx=s.player%W-origin%W, dy=s.player/W-origin/W;
    if(abs(dx)>6 || abs(dy)>6) return false;
    if(!MONSTER_WAKE_LOS) return true;
    int bit=(dy+8)*17+dx+8;
    return (t.los[(size_t(s.map_id)*N+origin)*10+bit/32]>>(bit%32))&1;
}
HD bool visible_enemy(const State &s, const Config &c, const Tables &t) {
    for(int i=0;i<c.count;i++) if(s.hp[i]>0 && in_view(s,t,s.pos[i])) return true;
    return false;
}
HD void update_knowledge(State &s, const Config &c, const Tables &t) {
    for(int i=0;i<c.count;i++) if(s.hp[i]>0) {
        bool visible=in_view(s,t,s.pos[i]);
        if(visible) s.encountered[i]=1;
        if((visible || GLOBAL_ENEMIES) && s.enemy_slot[i]<0) s.enemy_slot[i]=s.next_slot++;
    }
}
#ifdef KNOWN_FRONTIER
// BFS may traverse only revealed floor. Unknown terrain never participates in
// choosing the closest frontier, unlike the original full-map distance field.
HD void known_distances(const State &s, const Tables &t, uint16_t *ds, bool nearest_only=false) {
    int16_t queue[N];
    for(int p=0;p<N;p++) ds[p]=65535;
    int head=0, tail=1;
    queue[0]=s.player; ds[s.player]=0;
#if defined(FAST_FRONTIER) && defined(FRONTIER_ROUTE_CUE_OBS)
    if(nearest_only && s.frontier_count==0) return;
#endif
    while(head<tail) {
        int p=queue[head++];
#if defined(FAST_FRONTIER) && defined(FRONTIER_ROUTE_CUE_OBS)
        // FIFO BFS has discovered the entire nearest-frontier distance layer
        // when its first frontier is dequeued. Keep those distances so the
        // existing frontier-list tie break and route backtracking stay intact.
        int slot=s.frontier_slot[p];
        if(nearest_only && slot>=0 && slot<s.frontier_count && s.frontier_cells[slot]==p) break;
#endif
        for(int d=0;d<8;d++) {
            int q=neighbor(p,d);
            if(q>=0 && s.viewed[q] && floor_at(t,s.map_id,q) && ds[q]==65535) {
                ds[q]=ds[p]+1; queue[tail++]=q;
            }
        }
    }
}
#ifdef FRONTIER_ROUTE_CUE_OBS
HD int route_first_step(int player, int target, const uint16_t *ds) {
    if(target<0 || ds[target]==65535 || target==player) return -1;
    // Walk the player-rooted distance field backwards from the target.
    // Every predecessor was reached through observed floor by the BFS.
    int p=target;
    while(ds[p]>1) {
        int previous=-1;
        for(int d=0;d<8;d++) {
            int q=neighbor(p,d);
            if(q>=0 && int(ds[q])+1==ds[p]) { previous=q; break; }
        }
        if(previous<0) return -1;
        p=previous;
    }
    for(int d=0;d<8;d++) if(neighbor(player,d)==p) return d;
    return -1;
}
#endif
#endif
#ifdef EXPLORE_REWARD
#if defined(FRONTIER_MEMORY_OBS) || defined(FRONTIER_MEMORY_WALLS_OBS) || defined(FRONTIER_RING_MEMORY_WALLS_OBS)
HD bool frontier_anchor(const State &s, const Tables &t, int p) {
    if(p<0 || !floor_at(t,s.map_id,p) || !s.seen[p]) return false;
    for(int d=0;d<8;d++) {
        int q=neighbor(p,d);
#if defined(FRONTIER_MEMORY_WALLS_OBS) || defined(FRONTIER_RING_MEMORY_WALLS_OBS)
        if(q>=0 && !s.viewed[q]) return true;
#else
        if(q>=0 && floor_at(t,s.map_id,q) && !s.seen[q]) return true;
#endif
    }
    return false;
}
HD void refresh_frontier(State &s, const Tables &t, int p) {
    if(p<0) return;
    bool want=frontier_anchor(s,t,p);
    int slot=s.frontier_slot[p];
    if(want && slot<0) {
        int n=s.frontier_count++;
        s.frontier_cells[n]=p;
        s.frontier_slot[p]=n;
    } else if(!want && slot>=0) {
        int last=--s.frontier_count;
        int q=s.frontier_cells[last];
        s.frontier_cells[slot]=q;
        s.frontier_slot[q]=slot;
        s.frontier_slot[p]=-1;
    }
}
#endif
HD int reveal(State &s, const Tables &t) {
    int newly_seen=0;
    int changed_count=0;
    int changed[VIEW_CELLS];
    for(int y=-VIEW_RADIUS;y<=VIEW_RADIUS;y++) for(int x=-VIEW_RADIUS;x<=VIEW_RADIUS;x++) {
        int px=s.player%W+x, py=s.player/W+y;
        if(px<0 || px>=W || py<0 || py>=H) continue;
        int p=py*W+px;
        if(!in_view(s,t,p)) continue;
#ifdef MARK_WALLS
        if(!s.viewed[p]) {
            s.viewed[p]=1;
            changed[changed_count++]=p;
        }
#endif
        if(floor_at(t,s.map_id,p) && !s.seen[p]) {
            s.seen[p]=1;
            newly_seen++;
#ifndef MARK_WALLS
            changed[changed_count++]=p;
#endif
        }
    }
#if defined(FRONTIER_MEMORY_OBS) || defined(FRONTIER_MEMORY_WALLS_OBS) || defined(FRONTIER_RING_MEMORY_WALLS_OBS)
    // Only a newly seen cell and its eight neighbors can change frontier
    // status. Refresh after marking the whole view so all tests use the same
    // updated memory state.
    for(int i=0;i<changed_count;i++) {
        int p=changed[i];
        refresh_frontier(s,t,p);
        for(int d=0;d<8;d++) refresh_frontier(s,t,neighbor(p,d));
    }
#endif
    s.floor_seen+=newly_seen;
    return newly_seen;
}
#endif
HD void reset(State &s, Config c, const Tables &t) {
    assert(c.count==REQUIRED+OGRE_COUNT);
    s.ogres_killed=s.ogre_damage=s.ogre_actions=s.ogre_adjacent_turns=s.ogre_fatal=0;
#ifdef HEAL_CHARGES
    s.charges=HEAL_CHARGES; s.heals_used=s.heal_hp_sum=s.restored_hp_sum=0;
#endif
#ifdef MULTI_MAP
    s.map_id=t.map_filter >= 0 ? t.map_filter : s.w.rng.r(t.n_maps);
#else
    s.map_id=0;
#endif
    int map_id=s.map_id;
    for (int p=0; p<N; p++) s.occ[p]=-1;
    s.player=cells_map(t,map_id)[s.w.rng.r(cell_count(t,map_id))];
    s.w.hp=c.hp; s.w.regen=0; s.w.blocks=0;
    s.ticks=0; s.killed=0; s.next_slot=0; s.floor_seen=0;
    for(int i=0;i<ENEMIES;i++) { s.enemy_slot[i]=-1; s.encountered[i]=0; }
    const int mhp[6]={8,10,12,16,12,10};
    for (int i=0;i<REQUIRED;i++) {
        int p;
        do { p=cells_map(t,map_id)[s.w.rng.r(cell_count(t,map_id))]; }
        while (p==s.player || s.occ[p]>=0);
        s.pos[i]=p; s.occ[p]=i; s.hp[i]=mhp[i%6];
        s.energy[i]=70+s.w.rng.r(10);
#ifdef SLEEP_ON
        s.awake[i]=0;
#endif
    }
    // Separate spawn RNG preserves player/regular placements and their combat RNG
    // across N=0/1/2. First ogre placement is identical for N=1 and N=2.
    RNG spawn=s.w.rng;
    for(int i=REQUIRED;i<c.count;i++) {
        int chosen=-1, eligible=0;
        for(int j=0;j<cell_count(t,map_id);j++) {
            int p=cells_map(t,map_id)[j];
            if(s.occ[p]<0 && cheb(p,s.player)>=12 && spawn.r(++eligible)==0) chosen=p;
        }
        assert(chosen>=0);
        s.pos[i]=chosen; s.occ[chosen]=i; s.hp[i]=48;
        s.awake[i]=0; s.energy[i]=70+spawn.r(10);
    }
#ifdef EXPLORE_REWARD
    for(int p=0;p<N;p++) s.seen[p]=0;
#ifdef MARK_WALLS
    for(int p=0;p<N;p++) s.viewed[p]=0;
#endif
#if defined(FRONTIER_MEMORY_OBS) || defined(FRONTIER_MEMORY_WALLS_OBS) || defined(FRONTIER_RING_MEMORY_WALLS_OBS)
    s.frontier_count=0;
    for(int p=0;p<N;p++) s.frontier_slot[p]=-1;
#endif
    reveal(s,t); // The initial observation does not earn exploration reward.
    update_knowledge(s,c,t);
#endif
}
HD void observe(State &s, Config c, const Tables &t, float *o, float *mask) {
    for(int j=0;j<OBS;j++) o[j]=0;
    for(int y=-VIEW_RADIUS;y<=VIEW_RADIUS;y++) for(int x=-VIEW_RADIUS;x<=VIEW_RADIUS;x++) {
        int px=s.player%W+x, py=s.player/W+y, j=(y+VIEW_RADIUS)*SIDE+x+VIEW_RADIUS;
        if(px<0 || px>=W || py<0 || py>=H) continue;
        int p=py*W+px;
        // Separate unknown, remembered wall/floor, and currently visible.
        o[j]=s.viewed[p] ? (floor_at(t,s.map_id,p) ? 1.f : -1.f) : 0.f;
        o[ORIGINAL_OBS-VIEW_CELLS+j]=in_view(s,t,p);
        int id=s.occ[p];
        if(id>=0 && (GLOBAL_ENEMIES || in_view(s,t,p))) o[VIEW_CELLS+j]=s.hp[id]/16.f;
    }
    for(int i=0;i<c.count;i++) if(s.hp[i]>0 && (GLOBAL_ENEMIES || in_view(s,t,s.pos[i]))) {
        assert(s.enemy_slot[i]>=0);
        int j=2*VIEW_CELLS+s.enemy_slot[i]*5;
        o[j]=(s.pos[i]%W-s.player%W)/80.f;
        o[j+1]=(s.pos[i]/W-s.player/W)/70.f;
        o[j+2]=s.hp[i]/16.f; o[j+3]=i>=REQUIRED ? 1.2f : (i%6)/5.f; o[j+4]=1;
    }
    // Fixed scales: never divide coverage by the hidden map's floor count.
    o[ORIGINAL_OBS]=PROGRESS_INPUT==1 ? (REQUIRED-s.killed)/24.f :
                    PROGRESS_INPUT==2 ? s.floor_seen/1024.f : 0.f;
    // Keep the player block after all monster slots.  The previous literals
    // (202..205) silently overwrote monster 8 when LEARN_ENEMIES=40.
    o[PLAYER_OBS]=s.w.hp/float(c.hp); o[PLAYER_OBS+1]=s.ticks/2048.f;
    o[PLAYER_OBS+2]=s.player%W/80.f; o[PLAYER_OBS+3]=s.player/W/70.f;
#ifdef SPATIAL_MAP_OBS
    for(int p=0;p<N;p++) {
        o[BASE_OBS+p]=floor_at(t,s.map_id,p);
        o[BASE_OBS+N+p]=s.seen[p];
        o[BASE_OBS+2*N+p]=(p==s.player);
        int id=s.occ[p];
        o[BASE_OBS+3*N+p]=(id>=0 && s.hp[id]>0) ? s.hp[id]/16.f : 0.f;
    }
#endif
#ifdef FULL_MAP_OBS
    for(int p=0;p<N;p++) o[BASE_OBS+p]=floor_at(t,s.map_id,p);
#endif
#ifdef SEEN_OBS
    for(int y=-VIEW_RADIUS;y<=VIEW_RADIUS;y++) for(int x=-VIEW_RADIUS;x<=VIEW_RADIUS;x++) {
        int px=s.player%W+x, py=s.player/W+y, j=(y+VIEW_RADIUS)*SIDE+x+VIEW_RADIUS;
        if(px<0 || px>=W || py<0 || py>=H) continue;
        o[BASE_OBS+j]=s.seen[py*W+px] ? 1.f : 0.f;
    }
#endif
#ifdef FRONTIER_RING12_OBS
    // A 12x12 outer perimeter at Chebyshev radius 6, with corners omitted:
    // 11 top + 11 bottom + 11 left + 11 right = 44 values.
    for(int y=-6;y<=6;y++) for(int x=-6;x<=6;x++) {
        if(abs(x)!=6 && abs(y)!=6) continue;
        if(abs(x)==6 && abs(y)==6) continue;
        int j;
        if(y==-6) j=x+5;
        else if(y==6) j=11+x+5;
        else if(x==-6) j=22+y+5;
        else j=33+y+5;
        int px=s.player%W+x, py=s.player/W+y;
        if(px<0 || px>=W || py<0 || py>=H) continue;
        int p=py*W+px;
        o[BASE_OBS+j]=(floor_at(t,s.map_id,p) && !s.seen[p]) ? 1.f : 0.f;
    }
#elif defined(FRONTIER_RING_MEMORY_WALLS_OBS)
    for(int y=-RING_RADIUS;y<=RING_RADIUS;y++) for(int x=-RING_RADIUS;x<=RING_RADIUS;x++) {
        if(abs(x)!=RING_RADIUS && abs(y)!=RING_RADIUS) continue;
        int j;
        if(y==-RING_RADIUS) j=x+RING_RADIUS;
        else if(y==RING_RADIUS) j=2*RING_RADIUS+1+x+RING_RADIUS;
        else if(x==-RING_RADIUS) j=2*(2*RING_RADIUS+1)+y+RING_RADIUS-1;
        else j=2*(2*RING_RADIUS+1)+(2*RING_RADIUS-1)+y+RING_RADIUS-1;
        int px=s.player%W+x, py=s.player/W+y;
        if(px<0 || px>=W || py<0 || py>=H) continue;
        int p=py*W+px;
        if(s.viewed[p]) o[BASE_OBS+j]=floor_at(t,s.map_id,p) ? 1.f : -1.f;
    }
    int best=-1, best_dist=65535, best_unseen=0, best_dx=0, best_dy=0;
#ifdef KNOWN_FRONTIER
    uint16_t known_ds[N];
    known_distances(s,t,known_ds,true);
    const uint16_t *ds=known_ds;
#else
    const uint16_t *ds=field(t,s.map_id,s.player);
#endif
    for(int k=0;k<s.frontier_count;k++) {
        int p=s.frontier_cells[k], d=ds[p];
        if(d<best_dist) {
            best=p; best_dist=d; best_unseen=0; best_dx=0; best_dy=0;
            for(int nd=0;nd<8;nd++) {
                int q=neighbor(p,nd);
                if(q>=0 && !s.viewed[q]) {
                    best_unseen++;
                    if(best_unseen==1) {
                        best_dx=q%W-p%W;
                        best_dy=q/W-p/W;
                    }
                }
            }
        }
    }
    if(best>=0) {
        int b=FRONTIER_OBS;
        o[b+0]=1.f;
        o[b+1]=(best%W-s.player%W)/float(W);
        o[b+2]=(best/W-s.player/W)/float(H);
        o[b+3]=best_dist/float(W+H);
        o[b+4]=best_unseen/8.f;
        o[b+5]=best_dx;
        o[b+6]=best_dy;
#ifdef FRONTIER_ROUTE_CUE_OBS
        int direction=route_first_step(s.player,best,ds);
        if(direction>=0) o[b+7+direction]=1.f;
#endif
    }
#elif defined(FRONTIER_MEMORY_OBS) || defined(FRONTIER_MEMORY_WALLS_OBS)
    int best=-1, best_dist=65535, best_unseen=0, best_dx=0, best_dy=0;
    const uint16_t *ds=field(t,s.map_id,s.player);
    for(int k=0;k<s.frontier_count;k++) {
        int p=s.frontier_cells[k], d=ds[p];
        if(d<best_dist) {
            best=p; best_dist=d; best_unseen=0; best_dx=0; best_dy=0;
            for(int nd=0;nd<8;nd++) {
                int q=neighbor(p,nd);
#ifdef FRONTIER_MEMORY_WALLS_OBS
                if(q>=0 && !s.viewed[q]) {
#else
                if(q>=0 && floor_at(t,s.map_id,q) && !s.seen[q]) {
#endif
                    best_unseen++;
                    if(best_unseen==1) {
                        best_dx=q%W-p%W;
                        best_dy=q/W-p/W;
                    }
                }
            }
        }
    }
    if(best>=0) {
        o[BASE_OBS+0]=1.f;
        o[BASE_OBS+1]=(best%W-s.player%W)/float(W);
        o[BASE_OBS+2]=(best/W-s.player/W)/float(H);
        o[BASE_OBS+3]=best_dist/float(W+H);
        o[BASE_OBS+4]=best_unseen/8.f;
        o[BASE_OBS+5]=best_dx;
        o[BASE_OBS+6]=best_dy;
    }
#elif defined(FRONTIER_RING_WALLS_OBS)
    for(int y=-5;y<=5;y++) for(int x=-5;x<=5;x++) {
        if(abs(x)!=5 && abs(y)!=5) continue;
        int j;
        if(y==-5) j=x+5;
        else if(y==5) j=11+x+5;
        else if(x==-5) j=22+y+4;
        else j=31+y+4;
        int px=s.player%W+x, py=s.player/W+y;
        if(px<0 || px>=W || py<0 || py>=H) continue;
        int p=py*W+px;
        if(s.viewed[p]) o[BASE_OBS+j]=floor_at(t,s.map_id,p) ? 1.f : -1.f;
    }
#elif defined(FRONTIER_RING_OBS)
    for(int y=-5;y<=5;y++) for(int x=-5;x<=5;x++) {
        if(abs(x)!=5 && abs(y)!=5) continue;
        int j;
        if(y==-5) j=x+5;
        else if(y==5) j=11+x+5;
        else if(x==-5) j=22+y+4;
        else j=31+y+4;
        int px=s.player%W+x, py=s.player/W+y;
        if(px<0 || px>=W || py<0 || py>=H) continue;
        int p=py*W+px;
        o[BASE_OBS+j]=(floor_at(t,s.map_id,p) && !s.seen[p]) ? 1.f : 0.f;
    }
#endif
#ifdef MONSTER_AWAKE_OBS
    for(int i=0;i<c.count;i++) if(s.hp[i]>0)
        o[BASE_OBS+55+i]=s.awake[i] ? 1.f : 0.f;
#endif
    for(int d=0;d<8;d++) { int q=neighbor(s.player,d); mask[d]=q>=0 && (!s.viewed[q] || floor_at(t,s.map_id,q)); }
    mask[8]=1;
    if(FRONTIER_TRAVEL) mask[9]=best>=0 && best_dist>0 && best_dist<65535 && !visible_enemy(s,c,t);
#ifdef HEAL_CHARGES
    o[OBS-1]=float(s.charges)/7.f;
    mask[9]=s.charges>0 && s.w.hp>0 && s.w.hp<c.hp;
#endif
}
// Task horizon is a terminal deadline, included in the observation. No bootstrap at timeout.
HD void primitive_transition(State &s, Config c, const Tables &t, int action, int limit, float *out) {
    for(int j=0;j<OUT;j++) out[j]=0;
#ifdef EXPLORE_REWARD
    int reward_milli=-1;
#else
    float reward=-0.001f;
#endif
    s.w.blocks=0;
#ifdef HEAL_CHARGES
    if(action==9 && s.charges>0 && s.w.hp>0 && s.w.hp<c.hp) {
        s.charges--; s.heals_used++; s.heal_hp_sum+=s.w.hp;
        s.restored_hp_sum+=c.hp-s.w.hp;
        s.w.hp=c.hp;
        reward_milli-=50;
    }
#endif
    s.w.regen+=c.regen;
    while(s.w.regen>=100) { s.w.hp=mn(c.hp,s.w.hp+1); s.w.regen-=100; }
    if(action>=0 && action<8) {
        int p=neighbor(s.player,action);
        if(floor_at(t,s.map_id,p)) {
            int id=s.occ[p];
            if(id>=0) {
                s.encountered[id]=1;
                if(s.enemy_slot[id]<0) s.enemy_slot[id]=s.next_slot++;
                // 80% hit, uniform 1..4 damage, fixed 10-aut attack; no player XP.
                if(s.w.rng.r(5)!=0) {
                    s.hp[id]-=1+s.w.rng.r(4);
                    if(s.hp[id]<=0) {
                        s.hp[id]=0; s.occ[p]=-1; s.energy[id]=-30000;
                        if(id<REQUIRED) s.killed++; else s.ogres_killed++;
#ifdef EXPLORE_REWARD
                        reward_milli+=id<REQUIRED ? KILL_MILLI : 0;
#else
                        reward+=id<REQUIRED ? 0.001f*KILL_MILLI : 0.f;
#endif
                    }
                }
            } else s.player=p;
        }
    }
#ifdef EXPLORE_REWARD
    // One milli-unit is 0.001 reward; this ablation doubles the first-seen
    // bonus to 0.002 while retaining integer accumulation for exact parity.
    reward_milli += EXPLORE_MILLI*reveal(s,t);
#endif
    out[33]=visible_enemy(s,c,t); // Also catch sightings before monsters move.
    bool clear=s.killed==REQUIRED;
    auto a=access(s,c.count);
    c.player=s.player;
    Map m={floor_map(t,s.map_id),field(t,s.map_id,s.player),nullptr,nullptr};
    if(!clear) {
#ifdef SLEEP_ON
        for(int i=0;i<c.count;i++)
            if(s.hp[i]>0 && !s.awake[i] && monster_detects_player(s,t,s.pos[i])) {
                s.awake[i]=1;
                if(i>=REQUIRED) out[21]++;
                s.energy[i]=70;
            }
        for(int i=0;i<c.count;i++)
            if(s.hp[i]>0 && !s.awake[i])
                s.energy[i]=-30000;
#endif
        bool adjacent=false;
        for(int i=0;i<c.count;i++) if(s.hp[i]>0) {
            s.energy[i]+=monster_kind(c,i).speed;
            if(i>=REQUIRED) adjacent |= cheb(s.pos[i],s.player)==1;
        }
        s.ogre_adjacent_turns+=adjacent;
        // Once per player turn, after wake checks and before monster actions.
        // Count a turn once even if both living awake ogres are nearby.
        for(int i=REQUIRED;i<c.count;i++) if(s.hp[i]>0 && s.awake[i]) {
            int d=cheb(s.pos[i],s.player);
            if(d<=1) out[22]=1;
            if(d<=3) out[23]=1;
        }
        while(s.w.hp>0) {
            int id=scan(a,c.count);
            if(id<0) break;
            Config active=c;
            active.kinds[id%6]=monster_kind(c,id);
            int before=s.w.hp;
            act(s.w,a,active,m,id);
            if(in_view(s,t,s.pos[id])) out[33]=1;
            if(id>=REQUIRED) {
                s.ogre_actions++; s.ogre_damage+=before-s.w.hp;
                if(s.w.hp<=0) s.ogre_fatal=1;
            }
        }
    }
    s.ticks++;
    bool death=s.w.hp<=0, timeout=!clear && !death && s.ticks>=limit;
    if(clear) {
#ifdef EXPLORE_REWARD
        reward_milli+=CLEAR_PER_ENEMY_MILLI ? CLEAR_PER_ENEMY_MILLI*c.count : CLEAR_MILLI;
#else
        reward+=CLEAR_PER_ENEMY_MILLI ? 0.001f*CLEAR_PER_ENEMY_MILLI*c.count : 0.001f*CLEAR_MILLI;
#endif
    }
    if(death) {
#ifdef EXPLORE_REWARD
        reward_milli-=DEATH_MILLI;
#else
        reward-=0.001f*DEATH_MILLI;
#endif
    }
#ifdef EXPLORE_REWARD
    float reward=0.001f*float(reward_milli);
#endif
    out[26]=1;
    out[33]=out[33] || visible_enemy(s,c,t);
    update_knowledge(s,c,t);
    for(int i=0;i<REQUIRED;i++) {
        out[8]+=s.encountered[i]!=0;
        out[9]+=s.hp[i]>0 && !s.encountered[i];
        out[10]+=s.hp[i]>0 && s.encountered[i];
        out[12]+=s.hp[i]>0 && in_view(s,t,s.pos[i]);
    }
    out[13]=s.floor_seen;
    out[11]=out[13]/cell_count(t,s.map_id);
    out[0]=reward; out[1]=clear||death||timeout; out[2]=clear;
    out[3]=s.killed; out[4]=mx(0,s.w.hp); out[5]=s.ticks;
    out[6]=death; out[7]=timeout;
    out[14]=s.ogres_killed; out[15]=s.ogre_damage; out[16]=s.ogre_actions;
    out[17]=s.ogre_adjacent_turns; out[20]=s.ogre_fatal;
    for(int i=REQUIRED;i<c.count;i++) {
        out[24]+=s.encountered[i]!=0;
        if(s.hp[i]>0) { out[18]+=s.awake[i]; out[19]++; out[25]+=in_view(s,t,s.pos[i]); }
    }

#ifdef HEAL_CHARGES
    out[8]=s.heals_used; out[9]=s.heal_hp_sum;
    out[10]=s.charges; out[11]=s.restored_hp_sum;
#endif
    if(out[1]) { s.w.episode++; reset(s,c,t); }
}
// Select the same nearest frontier/tie break as the observation. The route
// is fixed at activation and uses only remembered floor, never hidden geometry.
HD int travel_route(const State &s, const Config &c, const Tables &t, int16_t *route) {
    if(visible_enemy(s,c,t)) return 0;
    uint16_t ds[N]; known_distances(s,t,ds,true);
    int target=-1, distance=65535;
    for(int k=0;k<s.frontier_count;k++) {
        int p=s.frontier_cells[k];
        if(ds[p]<distance) { target=p; distance=ds[p]; }
    }
    if(target<0 || distance==0 || distance==65535) return 0;
    int p=target;
    for(int j=distance-1;j>=0;j--) {
        route[j]=p;
        int previous=-1;
        for(int d=0;d<8;d++) {
            int q=neighbor(p,d);
            if(q>=0 && int(ds[q])+1==ds[p]) { previous=q; break; }
        }
        if(previous<0) return 0;
        p=previous;
    }
    return distance;
}
HD void transition(State &s, Config c, const Tables &t, int action, int limit, float *out) {
    if(!FRONTIER_TRAVEL || action!=9) { primitive_transition(s,c,t,action,limit,out); return; }
    int16_t route[N];
    int length=travel_route(s,c,t,route);
    // Normally unreachable because the policy mask forbids it. Invalid direct
    // calls still cost a wait turn; they cannot create zero-time transitions.
    if(length==0) { primitive_transition(s,c,t,8,limit,out); out[32]=1; return; }
    float reward=0, events[3]={0,0,0};
    int elapsed=0, reached=0, interrupted=0, terminal=0, blocked=0;
    for(int j=0;j<length;j++) {
        int next=route[j], direction=-1;
        for(int d=0;d<8;d++) if(neighbor(s.player,d)==next) { direction=d; break; }
        if(direction<0 || !s.viewed[next] || !floor_at(t,s.map_id,next) || s.occ[next]>=0) {
            blocked=1; break;
        }
        primitive_transition(s,c,t,direction,limit,out);
        elapsed++; reward+=out[0];
        for(int k=0;k<3;k++) events[k]+=out[21+k];
        reached=j==length-1;
        interrupted=out[33]!=0;
        terminal=out[1]!=0;
        // Stop before issuing another movement, including after auto-reset.
        if(interrupted || terminal) break;
    }
    if(elapsed==0) { primitive_transition(s,c,t,8,limit,out); out[32]=1; return; }
    out[0]=reward;
    for(int k=0;k<3;k++) out[21+k]=events[k];
    out[26]=elapsed; out[27]=1; out[28]=elapsed;
    out[29]=reached; out[30]=interrupted; out[31]=terminal;
    out[32]=blocked;
}
HD int heuristic(State &s, Config c, const Tables &t) {
    // Full-map shortest-path pursuit; attack the weakest adjacent enemy first.
    int best=-1, bhp=10000;
    for(int d=0;d<8;d++) {
        int p=neighbor(s.player,d);
        if(p>=0 && s.occ[p]>=0 && s.hp[s.occ[p]]<bhp) {
            bhp=s.hp[s.occ[p]]; best=d;
        }
    }
    if(best>=0) return best;
    const uint16_t *ds=field(t,s.map_id,s.player);
    int target=-1, bd=65535;
    for(int i=0;i<c.count;i++) if(s.hp[i]>0 && ds[s.pos[i]]<bd) {
        bd=ds[s.pos[i]]; target=s.pos[i];
    }
    if(target<0) return 8;
    ds=field(t,s.map_id,target); bd=ds[s.player]; best=8;
    for(int d=0;d<8;d++) {
        int p=neighbor(s.player,d);
        if(floor_at(t,s.map_id,p) && ds[p]<bd) { bd=ds[p]; best=d; }
    }
    return best;
}
__global__ void init_kernel(State *s,int n,Config c,Tables t,uint64_t seed,float *obs,float *mask) {
    int i=blockIdx.x*blockDim.x+threadIdx.x; if(i>=n) return;
#ifdef MULTI_MAP
    // Balanced initial episodes for evaluation; ordinary training uses -1.
    if(t.map_filter==-2) t.map_filter=i%t.n_maps;
#endif
    s[i]={}; s[i].w.rng.seed(mix(seed+i),i+1); reset(s[i],c,t);
    observe(s[i],c,t,obs+i*OBS,mask+i*ACTIONS);
}
__global__ void step_kernel(State *s,int n,Config c,Tables t,const int64_t *actions,int limit,
                            float *obs,float *mask,float *out,const bool *active=nullptr) {
    int i=blockIdx.x*blockDim.x+threadIdx.x; if(i>=n) return;
    if(active && !active[i]) return;
    transition(s[i],c,t,actions[i],limit,out+i*OUT);
    observe(s[i],c,t,obs+i*OBS,mask+i*ACTIONS);
}
__global__ void heuristic_kernel(State *s,int n,Config c,Tables t,int64_t *actions) {
    int i=blockIdx.x*blockDim.x+threadIdx.x; if(i<n) actions[i]=heuristic(s[i],c,t);
}
} // namespace learn
using namespace learn;
extern "C" {
int learn_state_bytes() { return sizeof(State); }
int learn_obs_size() { return OBS; }
int learn_action_size() { return ACTIONS; }
int learn_out_size() { return OUT; }
int learn_config_bytes() { return sizeof(Config); }
int learn_init(State *s,int n,Config *c,Tables *t,uint64_t seed,float *obs,float *mask,void *stream,int gpu) {
    if(gpu) { init_kernel<<<(n+BLOCK_SIZE-1)/BLOCK_SIZE,BLOCK_SIZE,0,(cudaStream_t)stream>>>(s,n,*c,*t,seed,obs,mask); return cudaGetLastError(); }
    for(int i=0;i<n;i++) {
        Tables initial=*t;
#ifdef MULTI_MAP
        if(initial.map_filter==-2) initial.map_filter=i%initial.n_maps;
#endif
        s[i]={}; s[i].w.rng.seed(mix(seed+i),i+1); reset(s[i],*c,initial);
        observe(s[i],*c,*t,obs+i*OBS,mask+i*ACTIONS);
    }
    return 0;
}
int learn_step(State *s,int n,Config *c,Tables *t,const int64_t *a,int limit,float *obs,float *mask,float *out,void *stream,int gpu) {
    if(gpu) { step_kernel<<<(n+BLOCK_SIZE-1)/BLOCK_SIZE,BLOCK_SIZE,0,(cudaStream_t)stream>>>(s,n,*c,*t,a,limit,obs,mask,out); return cudaGetLastError(); }
    for(int i=0;i<n;i++) { transition(s[i],*c,*t,a[i],limit,out+i*OUT); observe(s[i],*c,*t,obs+i*OBS,mask+i*ACTIONS); }
    return 0;
}
int learn_step_active(State *s,int n,Config *c,Tables *t,const int64_t *a,int limit,float *obs,float *mask,float *out,const bool *active,void *stream,int gpu) {
    if(gpu) { step_kernel<<<(n+BLOCK_SIZE-1)/BLOCK_SIZE,BLOCK_SIZE,0,(cudaStream_t)stream>>>(s,n,*c,*t,a,limit,obs,mask,out,active); return cudaGetLastError(); }
    for(int i=0;i<n;i++) if(active[i]) { transition(s[i],*c,*t,a[i],limit,out+i*OUT); observe(s[i],*c,*t,obs+i*OBS,mask+i*ACTIONS); }
    return 0;
}
int learn_heuristic(State *s,int n,Config *c,Tables *t,int64_t *a,void *stream,int gpu) {
    if(gpu) { heuristic_kernel<<<(n+BLOCK_SIZE-1)/BLOCK_SIZE,BLOCK_SIZE,0,(cudaStream_t)stream>>>(s,n,*c,*t,a); return cudaGetLastError(); }
    for(int i=0;i<n;i++) a[i]=heuristic(s[i],*c,*t);
    return 0;
}
// Test hooks use the same helpers as native CPU and CUDA execution.
// Test a macro against an explicit sequence of primitive game turns.
void compare_travel(State initial, Config c, Tables t, int limit, float *macro_out) {
    State macro=initial, manual=initial;
    int16_t route[N]; int length=travel_route(initial,c,t,route); assert(length>0);
    float step[OUT], reward=0, events[3]={0,0,0}; int turns=0;
    for(int j=0;j<length;j++) {
        int d=-1;
        for(int k=0;k<8;k++) if(neighbor(manual.player,k)==route[j]) { d=k; break; }
        assert(d>=0);
        primitive_transition(manual,c,t,d,limit,step); turns++; reward+=step[0];
        for(int k=0;k<3;k++) events[k]+=step[21+k];
        if(step[1] || step[33]) break;
    }
    transition(macro,c,t,9,limit,macro_out);
    assert(memcmp(&macro,&manual,sizeof(State))==0);
    assert(macro_out[0]==reward && macro_out[26]==turns && macro_out[27]==1);
    for(int k=1;k<26;k++) {
        float expected=k>=21 && k<=23 ? events[k-21] : step[k];
        assert(macro_out[k]==expected);
    }
}
int learn_budget2048_test(Config *cp,Tables *tp) {
    Config c=*cp; Tables t=*tp; t.map_filter=0;
    State base={}; base.w.rng.seed(19,1); reset(base,c,t);
    for(int i=0;i<c.count;i++) { base.occ[base.pos[i]]=-1; base.hp[i]=0; }
    float out[OUT],obs[OBS],mask[ACTIONS];
    State s=base; s.ticks=511;
    transition(s,c,t,8,2048,out);
    assert(out[5]==512 && !out[1]);
    observe(s,c,t,obs,mask); assert(obs[PLAYER_OBS+1]==.25f);
    s=base; s.ticks=2046;
    transition(s,c,t,8,2048,out); assert(!out[1] && out[5]==2047);
    observe(s,c,t,obs,mask); assert(obs[PLAYER_OBS+1]==2047/2048.f);
    transition(s,c,t,8,2048,out); assert(out[1] && out[7] && out[5]==2048 && s.ticks==0);
    observe(s,c,t,obs,mask); assert(obs[PLAYER_OBS+1]==0);
    return 0;
}
int learn_travel_test(Config *cp,Tables *tp) {
    if(!FRONTIER_TRAVEL) return 0;
    Config c=*cp; Tables t=*tp; t.map_filter=0;
    State base={}; int16_t route[N]; int length=0;
    for(int seed=0;seed<100 && length<3;seed++) {
        base={}; base.w.rng.seed(seed,1); reset(base,c,t);
        for(int i=0;i<c.count;i++) { base.occ[base.pos[i]]=-1; base.hp[i]=0; }
        length=travel_route(base,c,t,route);
    }
    assert(length>=3);
    float out[OUT],obs[OBS],mask[ACTIONS];
    observe(base,c,t,obs,mask); assert(mask[9]==1);
    compare_travel(base,c,t,512,out);
    assert(out[26]==length && out[29]==1 && out[30]==0 && out[1]==0);
    // Underlying deadline terminates the trip without stepping the reset world.
    State deadline=base; deadline.ticks=511;
    compare_travel(deadline,c,t,512,out);
    assert(out[26]==1 && out[7]==1 && out[31]==1 && out[29]==0);
    // A currently visible foe masks the macro, and leaving sight enables it.
    State visible=base; int adjacent=-1;
    for(int d=0;d<8;d++) if(floor_at(t,0,neighbor(base.player,d))) { adjacent=neighbor(base.player,d); break; }
    assert(adjacent>=0);
    visible.pos[0]=adjacent; visible.hp[0]=8; visible.occ[adjacent]=0;
    update_knowledge(visible,c,t);
    observe(visible,c,t,obs,mask); assert(mask[9]==0);
    State waited=visible; float waited_out[OUT];
    primitive_transition(waited,c,t,8,512,waited_out);
    transition(visible,c,t,9,512,out);
    assert(memcmp(&visible,&waited,sizeof(State))==0 && out[32]==1 && out[26]==1);
    visible=base; observe(visible,c,t,obs,mask); assert(mask[9]==1);
    // Find an initially hidden foe that becomes visible partway along the route.
    bool interrupted=false;
    for(int j=0;j<cell_count(t,0) && !interrupted;j++) {
        int p=cells_map(t,0)[j];
        if(in_view(base,t,p)) continue;
        State hidden=base; hidden.pos[0]=p; hidden.hp[0]=8;
        hidden.occ[p]=0; hidden.awake[0]=0; hidden.energy[0]=70;
        State trial=hidden; transition(trial,c,t,9,512,out);
        if(out[30] && out[26]<length) {
            compare_travel(hidden,c,t,512,out); interrupted=true;
            assert(out[26]>=1 && out[29]==0);
            observe(trial,c,t,obs,mask);
            assert(mask[9]==!visible_enemy(trial,c,t));
        }
    }
    assert(interrupted);
    // No reachable frontier means unavailable, not a zero-time action.
    State finished=base; finished.frontier_count=0;
    for(int p=0;p<N;p++) finished.frontier_slot[p]=-1;
    observe(finished,c,t,obs,mask); assert(mask[9]==0);
    transition(finished,c,t,9,512,out); assert(out[26]==1 && out[32]==1);
    return 0;
}
int learn_ogre_test(Config *cp,Tables *tp) {
    Config c=*cp; Tables t=*tp;
    for(int map=0;map<t.n_maps;map++) {
        t.map_filter=map;
        for(int seed=0;seed<16;seed++) {
            State s={}; s.w.rng.seed(seed,1); reset(s,c,t);
            for(int i=REQUIRED;i<c.count;i++) {
                assert(cheb(s.pos[i],s.player)>=12 && s.hp[i]==48 && !s.awake[i]);
                assert(s.occ[s.pos[i]]==i && s.enemy_slot[i]==-1 && !s.encountered[i]);
                Kind k=monster_kind(c,i);
                assert(k.speed==5 && k.damage==24 && k.tohit==30 && k.bypass==25);
            }
        }
    }
    if(!OGRE_COUNT) return 0;
    t.map_filter=0;
    State s={}; s.w.rng.seed(42,1); reset(s,c,t);
    // Isolate one awake ogre, still far away: energy accrues in steps of five,
    // and an action costs ten. Check two successive two-turn cycles.
    for(int i=0;i<c.count;i++) if(i!=REQUIRED) { s.occ[s.pos[i]]=-1; s.hp[i]=0; }
    s.awake[REQUIRED]=1; s.energy[REQUIRED]=70;
    float out[OUT];
    for(int turn=1;turn<=4;turn++) {
        transition(s,c,t,8,512,out);
        assert(s.ogre_actions==turn/2);
        assert(s.energy[REQUIRED]==(turn%2 ? 75 : 70));
        assert(out[21]==0);
    }
    // An optional ogre kill gives no kill reward and does not complete a floor.
    reset(s,c,t);
    int d=-1;
    for(int k=0;k<8;k++) if(floor_at(t,0,neighbor(s.player,k))) { d=k; break; }
    assert(d>=0);
    for(int i=0;i<c.count;i++) { s.occ[s.pos[i]]=-1; s.hp[i]=0; }
    s.pos[REQUIRED]=neighbor(s.player,d); s.hp[REQUIRED]=1;
    s.occ[s.pos[REQUIRED]]=REQUIRED; s.awake[REQUIRED]=0;
    RNG trial=s.w.rng;
    while(trial.r(5)==0) { s.w.rng.next(); trial=s.w.rng; }
    transition(s,c,t,d,512,out);
    assert(out[14]==1 && out[3]==0 && out[2]==0);
    assert(fabsf(out[0]+.001f)<1e-6f);
    // Killing the final required enemy clears with both ogres still alive.
    reset(s,c,t);
    for(int i=0;i<REQUIRED;i++) { s.occ[s.pos[i]]=-1; s.hp[i]=0; }
    s.killed=REQUIRED-1;
    d=-1;
    for(int k=0;k<8;k++) if(floor_at(t,0,neighbor(s.player,k))) { d=k; break; }
    assert(d>=0);
    s.pos[0]=neighbor(s.player,d); s.hp[0]=1; s.occ[s.pos[0]]=0;
    trial=s.w.rng;
    while(trial.r(5)==0) { s.w.rng.next(); trial=s.w.rng; }
    transition(s,c,t,d,512,out);
    assert(out[2]==1 && out[3]==24 && out[19]==OGRE_COUNT && out[14]==0);
    assert(fabsf(out[0]-3.999f)<1e-6f);
    return 0;
}
int learn_semantic_test(Config *cp,Tables *tp) {
    Config c=*cp; Tables t=*tp; t.map_filter=0;
    State s={}; s.w.rng.seed(99,1); reset(s,c,t);
    float a[OBS], b[OBS], ma[ACTIONS], mb[ACTIONS];
    int occluded=0, detected=0, distant=0;
    for(int map=0;map<t.n_maps;map++) {
        s.map_id=map;
        for(int j=0;j<cell_count(t,map);j++) {
            int origin=cells_map(t,map)[j];
            for(int dy=-8;dy<=8;dy++) for(int dx=-8;dx<=8;dx++) {
                int x=origin%W+dx,y=origin/W+dy;
                if(x<0 || x>=W || y<0 || y>=H) continue;
                s.player=y*W+x;
                if(!floor_at(t,map,s.player)) continue;
                int bit=(dy+8)*17+dx+8;
                bool los=(t.los[(size_t(map)*N+origin)*10+bit/32]>>(bit%32))&1;
                bool near=abs(dx)<=6 && abs(dy)<=6;
                assert(monster_detects_player(s,t,origin)==(near && (!MONSTER_WAKE_LOS || los)));
                if(map==0 && origin!=s.player && ((near && !los && occluded==0) ||
                   (near && los && detected==1) || (!near && los && distant==0))) {
                    State probe=s;
                    for(int k=0;k<N;k++) probe.occ[k]=-1;
                    for(int k=0;k<c.count;k++) { probe.hp[k]=0; probe.awake[k]=0; }
                    probe.pos[0]=origin; probe.hp[0]=16; probe.occ[origin]=0;
                    probe.energy[0]=-30000;
                    float out[OUT];
                    transition(probe,c,t,8,512,out);
                    assert(bool(probe.awake[0])==(near && (!MONSTER_WAKE_LOS || los)));
                    if(!(near && (!MONSTER_WAKE_LOS || los))) assert(probe.pos[0]==origin && probe.w.hp==s.w.hp);
                }
                occluded+=near && !los; detected+=near && los; distant+=!near && los;
            }
        }
    }
    assert(occluded>0 && detected>0 && distant>0);
    s.map_id=0;
    // Locate a position with a floor hidden behind a wall inside radius seven.
    int blocked=-1;
    for(int j=0;j<cell_count(t,0) && blocked<0;j++) {
        s.player=cells_map(t,0)[j];
        for(int y=-VIEW_RADIUS;y<=VIEW_RADIUS;y++) for(int x=-VIEW_RADIUS;x<=VIEW_RADIUS;x++) {
            int xx=s.player%W+x, yy=s.player/W+y;
            if(xx<0 || xx>=W || yy<0 || yy>=H) continue;
            int p=yy*W+xx, bit=(y+8)*17+x+8;
            if(floor_at(t,0,p) && !((t.los[s.player*10+bit/32]>>(bit%32))&1)) blocked=p;
        }
    }
    assert(blocked>=0);
    // Refresh memory at the selected point, not the old spawn.
    for(int p=0;p<N;p++) { s.seen[p]=s.viewed[p]=0; s.frontier_slot[p]=-1; s.occ[p]=-1; }
    s.frontier_count=s.floor_seen=0;
    for(int i=0;i<c.count;i++) { s.hp[i]=0; s.enemy_slot[i]=-1; s.encountered[i]=0; }
    s.next_slot=0; reveal(s,t);
    assert(s.viewed[blocked]==!TERRAIN_LOS);
    assert(in_view(s,t,s.player));
    int hidden=-1, hidden2=-1, visible=-1;
    for(int j=0;j<cell_count(t,0);j++) {
        int p=cells_map(t,0)[j];
        if(!in_view(s,t,p)) { hidden2=hidden; hidden=p; }
        else if(p!=s.player) visible=p;
    }
    assert(hidden>=0 && hidden2>=0 && visible>=0);
    // Discovery records are allocated on sight, not at original roster indices.
    int id=c.count-1;
    s.pos[id]=visible; s.hp[id]=8; s.occ[visible]=id; update_knowledge(s,c,t);
    assert(s.enemy_slot[id]==0 && s.encountered[id]);
    observe(s,c,t,a,ma); assert(a[2*VIEW_CELLS+4]==1);
    // Leaving sight removes live information in partial-observation variants.
    s.occ[visible]=-1; s.pos[id]=hidden; s.occ[hidden]=id;
    update_knowledge(s,c,t); observe(s,c,t,a,ma);
    assert(a[2*VIEW_CELLS+4]==GLOBAL_ENEMIES);
    s.occ[hidden]=-1; s.pos[id]=hidden2; s.hp[id]=3; s.occ[hidden2]=id;
    update_knowledge(s,c,t); observe(s,c,t,b,mb);
    if(!GLOBAL_ENEMIES) {
        assert(memcmp(a,b,sizeof(a))==0 && memcmp(ma,mb,sizeof(ma))==0);
    } else assert(memcmp(a,b,sizeof(a))!=0);
    // An undiscovered monster cannot allocate an exposed record or reveal its slot.
    if(!GLOBAL_ENEMIES) {
        s.enemy_slot[id]=-1; s.encountered[id]=0; s.next_slot=0;
        update_knowledge(s,c,t); assert(s.next_slot==0 && !s.encountered[id]);
    }
    // Unknown distant geometry cannot change present memory or frontier hints.
    observe(s,c,t,a,ma);
    uint8_t *floor=const_cast<uint8_t *>(t.floor);
    assert(!s.viewed[hidden]); uint8_t old=floor[hidden]; floor[hidden]=!old;
    observe(s,c,t,b,mb); assert(memcmp(a,b,sizeof(a))==0 && memcmp(ma,mb,sizeof(ma))==0);
    floor[hidden]=old;
    // Currently visible and remembered floor/wall codes agree; unknown stays zero.
    observe(s,c,t,a,ma);
    for(int y=-VIEW_RADIUS;y<=VIEW_RADIUS;y++) for(int x=-VIEW_RADIUS;x<=VIEW_RADIUS;x++) {
        int xx=s.player%W+x, yy=s.player/W+y, j=(y+VIEW_RADIUS)*SIDE+x+VIEW_RADIUS;
        if(xx<0 || xx>=W || yy<0 || yy>=H) continue;
        int p=yy*W+xx;
        assert(a[ORIGINAL_OBS-VIEW_CELLS+j]==in_view(s,t,p));
        assert(a[j]==(s.viewed[p] ? (floor[p] ? 1.f : -1.f) : 0.f));
    }
    // Masking an unknown neighboring tile must not disclose its true terrain.
    for(int d=0;d<8;d++) {
        int p=neighbor(s.player,d); if(p<0) continue;
        uint8_t viewed=s.viewed[p]; s.viewed[p]=0;
        observe(s,c,t,a,ma); assert(ma[d]==1); s.viewed[p]=viewed;
    }
    return 0;
}
}

extern "C" int learn_progress_test(Config *config,Tables *tables){
 State s={};s.w.rng.seed(42,1);reset(s,*config,*tables);
 float a[OBS],b[OBS],mask[ACTIONS];
 for(int k=0;k<=24;k++){
  s.killed=k;s.floor_seen=1234;observe(s,*config,*tables,a,mask);
  float expected=PROGRESS_INPUT==1 ? (24-k)/24.f : PROGRESS_INPUT==2 ? 1234/1024.f : 0.f;
  assert(a[ORIGINAL_OBS]==expected);
  s.floor_seen=512;observe(s,*config,*tables,b,mask);
  for(int j=0;j<ORIGINAL_OBS;j++)assert(a[j]==b[j]);
  if(PROGRESS_INPUT==2)assert(b[ORIGINAL_OBS]==0.5f);
 }
 return 0;
}
__global__ void progress_counts_kernel(const State*s,int n,int *out){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 int alive=0,seen=0;
 for(int j=0;j<REQUIRED;j++)alive+=s[i].hp[j]>0;
 for(int j=0;j<N;j++)seen+=s[i].seen[j]!=0;
 out[i*2]=alive;out[i*2+1]=seen;
}
extern "C" int learn_progress_counts(const State*s,int n,int*out,void*stream){
 progress_counts_kernel<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,n,out);return cudaGetLastError();
}
