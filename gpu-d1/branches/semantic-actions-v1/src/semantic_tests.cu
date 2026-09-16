#include "learn.cu"
__device__ __noinline__ void isolated(State &s,Config c,Tables t,int hp){
 for(int i=0;i<sizeof(State);i++)((unsigned char*)&s)[i]=0;s.map_id=0;s.player=35*W+40;s.w.hp=hp;s.killed=REQUIRED-1;
 for(int p=0;p<N;p++){s.occ[p]=-1;s.frontier_slot[p]=-1;}
 for(int j=0;j<ENEMIES;j++){s.enemy_slot[j]=-1;s.energy[j]=-30000;}
 reveal(s,t);update_knowledge(s,c,t);
}
__device__ __noinline__ void put(State &s,Config c,Tables t,int id,int p,int hp,bool awake){s.pos[id]=p;s.hp[id]=hp;s.occ[p]=id;s.awake[id]=awake;update_knowledge(s,c,t);}
__device__ __noinline__ void test_transition(State &s,Config c,Tables t,int a,int limit,float *out){transition(s,c,t,a,limit,out);}
__device__ __noinline__ void test_primitive(State &s,Config c,Tables t,int a,int limit,float *out){primitive_transition(s,c,t,a,limit,out);}
__device__ __noinline__ void test_observe(State &s,Config c,Tables t,float *obs,float *mask){observe(s,c,t,obs,mask);}
__global__ void semantic_test_kernel(Config c,Tables t,int *result,State *storage){
 float out[OUT],obs[OBS],mask[ACTIONS],step[OUT];
 State &base=storage[0];isolated(base,c,t,3);test_observe(base,c,t,obs,mask);
 assert(!mask[0] && mask[1] && !mask[2] && mask[3] && mask[4]);
 // Rest equals primitive waits, including RNG, reward and regeneration; duration discount is exact.
 State &macro=storage[1],&manual=storage[2];macro=base;manual=base;test_transition(macro,c,t,4,2048,out);
 int count=0;float reward=0,discounted=0,factor=1;
 do{test_primitive(manual,c,t,8,2048,step);count++;reward+=step[0];discounted+=factor*step[0];factor*=.99f;}while(manual.w.hp<c.hp);
 manual.decisions=1;assert(out[0]==reward && out[40]==discounted && out[26]==count && out[35]==count && out[36] && !out[37]);
 const unsigned char*a=(const unsigned char*)&macro,*b=(const unsigned char*)&manual;for(int j=0;j<sizeof(State);j++)assert(a[j]==b[j]);
 test_observe(macro,c,t,obs,mask);assert(!mask[4] && obs[PLAYER_OBS+1]==count/2048.f);
 // Sleeping foe at seven tiles permits rest and remains asleep; six tiles wakes and interrupts.
 State &sleepy=storage[3];sleepy=base;put(sleepy,c,t,0,35*W+47,8,false);test_observe(sleepy,c,t,obs,mask);assert(mask[4] && !mask[1] && mask[2]);
 test_transition(sleepy,c,t,4,2048,out);assert(out[36] && !out[37] && !sleepy.awake[0]);
 State &waking=storage[4];waking=base;put(waking,c,t,0,35*W+46,8,false);test_transition(waking,c,t,4,2048,out);assert(out[26]==1 && out[37] && waking.awake[0]);
 test_observe(waking,c,t,obs,mask);assert(!mask[4]);
 // Exact physical deadline even inside a rest macro; terminal clock/reward retained before reset.
 State &deadline=storage[5];deadline=base;deadline.ticks=2047;test_transition(deadline,c,t,4,2048,out);assert(out[1] && out[7] && out[5]==2048 && out[26]==1 && deadline.ticks==0);
 // ATTACK is one primitive, with compass ties and weakest visible target selection.
 State &fight=storage[6];fight=base;fight.w.hp=c.hp;put(fight,c,t,0,35*W+41,8,true);put(fight,c,t,1,34*W+40,3,true);fight.killed=REQUIRED-2;
 assert(adjacent_attack(fight,c,t)==0);test_observe(fight,c,t,obs,mask);assert(mask[0] && !mask[1] && !mask[2] && !mask[4]);
 macro=fight;manual=fight;test_transition(macro,c,t,0,2048,out);test_primitive(manual,c,t,0,2048,step);manual.decisions=1;
 assert(out[26]==1 && out[0]==step[0]);a=(const unsigned char*)&macro;b=(const unsigned char*)&manual;for(int j=0;j<sizeof(State);j++)assert(a[j]==b[j]);
 // ENGAGE moves one known-floor step, never intentionally attacks.
 State &engage=storage[7];engage=base;put(engage,c,t,0,35*W+43,8,false);int d=engage_step(engage,c,t);assert(d>=0);int old=engage.player;test_transition(engage,c,t,2,2048,out);assert(engage.player==neighbor(old,d) && out[26]==1);
 // EXPLORE stops on any visible enemy, even if still asleep, and obeys deadline.
 State &explore=storage[8];explore=base;put(explore,c,t,0,35*W+48,8,false);assert(!visible_enemy(explore,c,t));test_observe(explore,c,t,obs,mask);assert(mask[1]);
 test_transition(explore,c,t,1,2048,out);assert(out[27] && out[30] && out[26]>=1 && visible_enemy(explore,c,t));
 State &walk=storage[9];walk=base;walk.ticks=2047;test_transition(walk,c,t,1,2048,out);assert(out[7] && out[5]==2048 && out[26]==1);
 // Invalid actions degrade to one ordinary wait, not a zero-time transition.
 State &invalid=storage[10];invalid=base;test_transition(invalid,c,t,0,2048,out);assert(out[26]==1 && invalid.ticks==1);
 *result=count;
}
extern "C" int semantic_self_test(Config*c,Tables*t,int*result,void*stream){State *storage;cudaMalloc(&storage,11*sizeof(State));semantic_test_kernel<<<1,1,0,(cudaStream_t)stream>>>(*c,*t,result,storage);auto error=cudaDeviceSynchronize();cudaFree(storage);return error;}
