// Semantic fixtures: expected inputs, not merely agreement between backends.
#include "learn.cu"
#include <cstdio>
int main() {
    uint8_t floor[N]; int16_t cells[N], index[N]; uint16_t distance[N];
    for(int p=0;p<N;p++) { floor[p]=1; cells[p]=p; index[p]=0; distance[p]=100; }
    Tables t={floor,cells,index,distance,N}; Config c={}; c.hp=20; c.count=0;
    State s={}; s.player=20*W+20; s.w.hp=20;
    for(int p=0;p<N;p++) {
        s.occ[p]=-1;
#if defined(FRONTIER_MEMORY_WALLS_OBS) || defined(FRONTIER_RING_MEMORY_WALLS_OBS)
        s.frontier_slot[p]=-1;
#endif
    }
    float o[OBS], before[OBS], mask[9];
    // Reveal records walls too, but exploration reward counts only fresh floor.
    floor[s.player+1]=0;
    assert(reveal(s,t)==80);
    assert(s.viewed[s.player+1] && !s.seen[s.player+1]);
    assert(s.seen[s.player] && reveal(s,t)==0);
#if defined(FRONTIER_RING_WALLS_OBS) || defined(FRONTIER_RING_MEMORY_WALLS_OBS)
    int p=s.player-5*W-5; // first outer-ring entry
    s.viewed[p]=0; floor[p]=1;
    observe(s,c,t,o,mask); assert(o[BASE_OBS]==0);
    floor[p]=0;
    observe(s,c,t,o,mask); assert(o[BASE_OBS]==0);
    s.viewed[p]=1;
    observe(s,c,t,o,mask); assert(o[BASE_OBS]==-1);
    floor[p]=1; s.seen[p]=1;
    observe(s,c,t,o,mask); assert(o[BASE_OBS]==1);
#ifdef FRONTIER_RING_MEMORY_WALLS_OBS
    // The combined variant keeps the same ring and appends the frontier
    // pointer at the next seven positions.
    for(int p=0;p<N;p++) {
        s.viewed[p]=1; s.seen[p]=0; s.frontier_slot[p]=-1;
    }
    s.frontier_count=0;
    int anchor=s.player+6, unknown=anchor+1;
    s.seen[anchor]=1; s.viewed[unknown]=0; distance[anchor]=6;
    refresh_frontier(s,t,anchor);
    assert(s.frontier_count==1);
    observe(s,c,t,o,mask);
    int b=BASE_OBS+40;
    assert(o[b]==1 && o[b+1]==6.f/W);
    assert(o[b+2]==0 && o[b+3]==6.f/(W+H));
    assert(o[b+4]==1.f/8 && o[b+5]==1 && o[b+6]==0);
    memcpy(before,o,sizeof(o)); floor[unknown]=0;
    refresh_frontier(s,t,anchor); observe(s,c,t,o,mask);
    assert(memcmp(before,o,sizeof(o))==0);
    s.viewed[unknown]=1; refresh_frontier(s,t,anchor);
    observe(s,c,t,o,mask);
    assert(s.frontier_count==0);
    for(int i=BASE_OBS+40;i<OBS;i++) assert(o[i]==0);
#endif
#else
    // One seen anchor and one unknown neighbor: all seven pointer fields
    // have explicit expected values. Unknown may contain either terrain.
    for(int p=0;p<N;p++) {
        s.viewed[p]=1; s.seen[p]=0; s.frontier_slot[p]=-1;
    }
    s.frontier_count=0;
    int anchor=s.player+6, unknown=anchor+1;
    s.seen[anchor]=1; s.viewed[unknown]=0; distance[anchor]=6;
    refresh_frontier(s,t,anchor);
    assert(s.frontier_count==1);
    observe(s,c,t,o,mask);
    assert(o[BASE_OBS]==1 && o[BASE_OBS+1]==6.f/W);
    assert(o[BASE_OBS+2]==0 && o[BASE_OBS+3]==6.f/(W+H));
    assert(o[BASE_OBS+4]==1.f/8 && o[BASE_OBS+5]==1 && o[BASE_OBS+6]==0);
    memcpy(before,o,sizeof(o)); floor[unknown]=0;
    refresh_frontier(s,t,anchor); observe(s,c,t,o,mask);
    assert(memcmp(before,o,sizeof(o))==0);
    s.viewed[unknown]=1; refresh_frontier(s,t,anchor);
    observe(s,c,t,o,mask);
    assert(s.frontier_count==0);
    for(int i=BASE_OBS;i<OBS;i++) assert(o[i]==0);
#endif
    puts("PASS wall observation semantic fixtures");
}
