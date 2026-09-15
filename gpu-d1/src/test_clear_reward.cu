#include "learn.cu"
#include <cmath>
#include <cstdio>
int main() {
    uint8_t floor[N]={}; int16_t cells[N]={}, index[N]={}; uint16_t distance[N]={};
    for(int p=0;p<N;p++) { floor[p]=1; cells[p]=p; }
    Tables t={floor,cells,index,distance,N};
    for(int count: {8,24,40}) {
        State s={}; Config c={}; c.hp=20; c.count=count;
        s.w.rng.seed(123,1); reset(s,c,t);
        for(int p=0;p<N;p++) s.seen[p]=s.viewed[p]=1;
        s.killed=count;
        for(int i=0;i<count;i++) s.hp[i]=0;
        float out[8]; transition(s,c,t,8,1024,out);
        float bonus=CLEAR_PER_ENEMY_MILLI ? .001f*CLEAR_PER_ENEMY_MILLI*count : 3.f;
        assert(out[1]==1 && out[2]==1 && out[6]==0);
        assert(std::fabs(out[0]-(bonus-.001f))<.000002f);
        assert(s.killed==0 && s.w.hp==c.hp);
    }
    puts("PASS: clear bonus at 8/24/40 initial enemies and terminal reset");
}
