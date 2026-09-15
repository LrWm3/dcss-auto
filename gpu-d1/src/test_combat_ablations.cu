#include "learn.cu"
#include <cstdio>
#include <cmath>
int main() {
    uint8_t floor[N]={}; int16_t cells[N]={}, index[N]={}; uint16_t distance[N]={};
    for(int p=0;p<N;p++) { floor[p]=1; cells[p]=p; index[p]=0; }
    Tables t={floor,cells,index,distance,N};
    State s={}; Config c={}; c.hp=20; c.count=1;
    s.w.rng.seed(123,1); reset(s,c,t);
    float obs[OBS], mask[9], out[8];
    s.awake[0]=0; observe(s,c,t,obs,mask);
    assert(obs[BASE_OBS+55]==0);
    s.awake[0]=1; observe(s,c,t,obs,mask);
    assert(obs[BASE_OBS+55]==1);
    s.hp[0]=0; observe(s,c,t,obs,mask);
    assert(obs[BASE_OBS+55]==0);
    reset(s,c,t);
    for(int p=0;p<N;p++) s.seen[p]=s.viewed[p]=1;
    s.w.hp=-100; s.w.regen=0;
    transition(s,c,t,8,1024,out);
    assert(out[6]==1 && out[1]==1 && s.w.hp==c.hp);
    assert(std::fabs(out[0] - (-0.001f * (DEATH_MILLI+1))) < 0.000001f);
    printf("PASS: awake/asleep/dead observation, death penalty %d, auto-reset\n", DEATH_MILLI);
}
