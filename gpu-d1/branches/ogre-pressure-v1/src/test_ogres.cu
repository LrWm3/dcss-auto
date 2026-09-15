#include "learn.cu"
#include <cmath>
#include <cstdio>
int main() {
    uint8_t floor[N]={}; int16_t cells[N]={}, index[N]={}; uint16_t distance[N]={};
    for(int p=0;p<N;p++) { floor[p]=1; cells[p]=p; }
    Tables t={floor,cells,index,distance,N};
    Config c={}; c.count=REQUIRED+OGRE_COUNT; c.hp=1000;
    State s={}; s.w.rng.seed(123,1); reset(s,c,t);
    float obs[OBS], mask[ACTIONS], out[OUT];
    for(int seed=0;seed<100;seed++) {
        reset(s,c,t);
        for(int i=REQUIRED;i<c.count;i++) {
            assert(cheb(s.player,s.pos[i])>=12);
            assert(s.hp[i]==48 && !s.awake[i]);
            for(int j=0;j<i;j++) assert(s.pos[i]!=s.pos[j]);
        }
    }
    if(OGRE_COUNT) {
        for(int p=0;p<N;p++) { s.occ[p]=-1; s.seen[p]=s.viewed[p]=1; }
        for(int i=0;i<c.count;i++) { s.hp[i]=0; s.energy[i]=-30000; }
        int id=REQUIRED; s.pos[id]=s.player+1; s.hp[id]=48;
        s.occ[s.pos[id]]=id; s.awake[id]=1; s.energy[id]=70;
        s.ogre_actions=0;
        for(int turn=1;turn<=10;turn++) {
            transition(s,c,t,8,1024,out);
            assert(s.ogre_actions==turn/2);
        }
        s.energy[id]=100; int before=s.ogre_actions;
        transition(s,c,t,8,1024,out);
        assert(s.ogre_actions-before==3); // Existing energy boosts preserved.
        observe(s,c,t,obs,mask);
        int j=BASE_OBS+55+id*8;
        assert(obs[j]==0 && obs[162+id*5+3]==1.2f);
        assert(obs[j+1]==float(bool(OGRE_FEATURES&1)));
        assert(obs[j+2]==((OGRE_FEATURES&2) ? .5f : 0.f));
        assert(obs[j+3]==float(bool(OGRE_FEATURES&4)));
        s.energy[id]=-30000; s.hp[id]=1;
        for(int attempt=0;attempt<100;attempt++) {
            transition(s,c,t,1,1024,out);
            if(s.hp[id]==0) break;
        }
        assert(s.hp[id]==0 && s.killed==0 && s.ogres_killed==1);
        assert(out[2]==0 && std::fabs(out[0]+.001f)<1e-6);
    }
    reset(s,c,t);
    for(int p=0;p<N;p++) s.seen[p]=s.viewed[p]=1;
    for(int i=0;i<REQUIRED;i++) s.hp[i]=0;
    s.killed=REQUIRED;
    transition(s,c,t,8,1024,out);
    assert(out[2]==1 && out[3]==24 && out[13]==OGRE_COUNT);
    assert(std::fabs(out[0]-2.999f)<1e-6);
    assert(s.killed==0 && s.ogres_killed==0 && s.ogre_actions==0);
    puts("PASS: distant spawn, energy cadence/boosts, optional kills, features, clear with living ogres, reset");
}
