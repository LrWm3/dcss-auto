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
__global__ void autoregressive_test_kernel(Config c,Tables t,int *result,State *storage){
 float out[OUT],obs[OBS],mask[ACTIONS],step[OUT];
 State &base=storage[0],&macro=storage[1],&manual=storage[2];isolated(base,c,t,3);
 test_observe(base,c,t,obs,mask);assert(mask[16] && mask[17]);
 for(int d=0;d<8;d++)assert(mask[d] && !mask[8+d]);
 // Rest and physical deadline agree with the semantic controller.
 macro=base;manual=base;test_transition(macro,c,t,17,2048,out);
 int count=0;float reward=0,discounted=0,factor=1;
 do{test_primitive(manual,c,t,8,2048,step);count++;reward+=step[0];discounted+=factor*step[0];factor*=1.f;}while(manual.w.hp<c.hp);
 manual.decisions=1;assert(out[0]==reward && out[40]==discounted && out[26]==count && out[36]);
 for(int j=0;j<sizeof(State);j++)assert(((unsigned char*)&macro)[j]==((unsigned char*)&manual)[j]);
 macro=base;macro.ticks=2047;test_transition(macro,c,t,17,2048,out);assert(out[7] && out[5]==2048 && out[26]==1);
 macro=base;put(macro,c,t,0,35*W+46,8,false);test_transition(macro,c,t,17,2048,out);assert(out[37] && out[26]==1);
 // Attack and movement directions are disjoint and translate to the same physics.
 macro=base;put(macro,c,t,0,35*W+41,8,true);test_observe(macro,c,t,obs,mask);
 assert(!mask[1] && mask[9] && !mask[17]);manual=macro;
 test_transition(macro,c,t,9,2048,out);test_primitive(manual,c,t,1,2048,step);manual.decisions=1;
 for(int j=0;j<sizeof(State);j++)assert(((unsigned char*)&macro)[j]==((unsigned char*)&manual)[j]);
 macro=base;manual=base;test_transition(macro,c,t,1,2048,out);test_primitive(manual,c,t,1,2048,step);manual.decisions=1;
 for(int j=0;j<sizeof(State);j++)assert(((unsigned char*)&macro)[j]==((unsigned char*)&manual)[j]);
 // Known walls disallow movement, unknown terrain does not leak wall knowledge.
 macro=base;macro.player=35*W+49;reveal(macro,t);test_observe(macro,c,t,obs,mask);assert(!mask[1]);
 macro.viewed[35*W+50]=0;test_observe(macro,c,t,obs,mask);assert(mask[1]);
 *result=count;
}
extern "C" int autoregressive_self_test(Config*c,Tables*t,int*result,void*stream){State *storage;cudaMalloc(&storage,3*sizeof(State));autoregressive_test_kernel<<<1,1,0,(cudaStream_t)stream>>>(*c,*t,result,storage);auto error=cudaDeviceSynchronize();cudaFree(storage);return error;}
