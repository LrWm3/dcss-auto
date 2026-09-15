#include "learn.cu"
#include <cstdio>
int main() {
    uint8_t floor[N]={}; int16_t cells[N]={}, index[N]={}; uint16_t distance[N]={};
    Tables t={floor,cells,index,distance,N};
    State s={}; Config c={}; c.hp=20; s.w.hp=20;
    s.player=20*W+20;
    for(int p=0;p<N;p++) s.occ[p]=-1;
    auto known=[&](int x,int y) { int p=y*W+x; floor[p]=1; s.viewed[p]=1; s.seen[p]=1; };
    uint16_t ds[N]; float obs[OBS], mask[9];
    auto check=[&](int target,int expected) {
        known_distances(s,t,ds);
        assert(route_first_step(s.player,target,ds)==expected);
        s.frontier_count=1; s.frontier_cells[0]=target;
        observe(s,c,t,obs,mask);
        for(int d=0;d<8;d++) assert(obs[BASE_OBS+47+d]==float(d==expected));
    };
    // Target east; the only exit is west, around a known wall.
    for(int x=18;x<=20;x++) known(x,20);
    for(int y=20;y<=24;y++) known(18,y);
    for(int x=18;x<=24;x++) known(x,24);
    for(int y=20;y<=24;y++) known(24,y);
    int target=20*W+24;
    check(target,3);
    // An unseen direct corridor cannot change the cue, whether floor or wall.
    for(int x=21;x<=23;x++) floor[20*W+x]=1;
    check(target,3);
    // Once observed, the direct corridor must give east instead.
    for(int x=21;x<=23;x++) known(x,20);
    check(target,1);
    check(s.player+1,1);
    check(s.player,-1);
    known(40,40); check(40*W+40,-1);
    s.frontier_count=0; observe(s,c,t,obs,mask);
    for(int d=0;d<8;d++) assert(obs[BASE_OBS+47+d]==0);
    puts("PASS route cue: detour, unknown shortcut, direct route, adjacent, at-target, unreachable, absent");
}
