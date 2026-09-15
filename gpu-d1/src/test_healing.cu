#include "learn.cu"
#include <cmath>
#include <cstdio>
int main() {
    uint8_t floor[N]={}; int16_t cells[N]={}, index[N]={}; uint16_t distance[N]={};
    for(int p=0;p<N;p++) { floor[p]=1; cells[p]=p; }
    Tables t={floor,cells,index,distance,N};
    State s={}; Config c={}; c.hp=20; c.count=1;
    s.w.rng.seed(123,1); reset(s,c,t);
    float obs[OBS], mask[ACTIONS], out[OUT];
    observe(s,c,t,obs,mask);
    assert(s.charges==HEAL_CHARGES && mask[9]==0);
    assert(std::fabs(obs[OBS-1]-float(HEAL_CHARGES)/7)<1e-6);
    for(int p=0;p<N;p++) s.seen[p]=s.viewed[p]=1;
    s.player=20*W+20; s.pos[0]=40*W+40; s.awake[0]=0;
    transition(s,c,t,9,1024,out); // Full HP: invalid action is harmless wait.
    assert(s.charges==HEAL_CHARGES && s.heals_used==0 && out[0]==-.001f);
    for(int use=0;use<HEAL_CHARGES;use++) {
        s.w.hp=5;
        observe(s,c,t,obs,mask); assert(mask[9]==1);
        int tick=s.ticks;
        transition(s,c,t,9,1024,out);
        assert(s.w.hp==20 && s.charges==HEAL_CHARGES-use-1 && s.ticks==tick+1);
        assert(s.heals_used==use+1 && s.heal_hp_sum==5*(use+1));
        assert(std::fabs(out[0]+.051f)<1e-6);
    }
    s.w.hp=5; observe(s,c,t,obs,mask); assert(mask[9]==0);
    transition(s,c,t,9,1024,out); assert(s.w.hp==5 && out[0]==-.001f);
    s.ticks=1023;
    transition(s,c,t,8,1024,out);
    assert(out[7]==1 && out[8]==HEAL_CHARGES && out[10]==0);
    assert(s.charges==HEAL_CHARGES && s.heals_used==0 && s.heal_hp_sum==0);
    if(HEAL_CHARGES) {
        // The same monster turn occurs after healing as after waiting.
        s.w.hp=10; s.player=20*W+20; s.pos[0]=s.player+1;
        s.awake[0]=1; s.energy[0]=70;
        c.kinds[0]={10,1,19,15};
        State waiting=s;
        transition(waiting,c,t,8,1024,out);
        transition(s,c,t,9,1024,out);
        assert(s.energy[0]==waiting.energy[0] && s.ticks==waiting.ticks);
        assert(s.w.s.actions==waiting.w.s.actions && s.w.s.actions>0);
        assert(s.w.hp-waiting.w.hp==10);
    }
    puts("PASS healing: masks, consumption, penalty, turn advancement, stats, terminal reset");
}
