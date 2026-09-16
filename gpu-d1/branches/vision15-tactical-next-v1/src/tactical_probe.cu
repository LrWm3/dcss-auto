// Scenario initialization only; unchanged movement, observations, rewards and combat.
#include "learn.cu"
__global__ void tactical_reset_kernel(State*s,int n,Config c,Tables t,const int*meta,const uint8_t*selected,float*obs,float*mask){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n || (selected && !selected[i]))return;
 State&v=s[i];RNG rng=v.w.rng;int map=v.map_id;int episode=v.w.episode;
 v={};v.w.rng=rng;v.w.episode=episode;v.map_id=map;
 const int*row=meta+map*8;
 v.player=row[0];v.w.hp=6+v.w.rng.r(13);v.ticks=256*v.w.rng.r(3);
 for(int p=0;p<N;p++){v.occ[p]=-1;v.frontier_slot[p]=-1;}
 for(int j=0;j<ENEMIES;j++){v.enemy_slot[j]=-1;v.energy[j]=-30000;}
 const int hp[6]={8,10,12,16,12,10};int count=v.w.rng.r(2)?3:6;int kind=v.w.rng.r(2)?3:0;
 v.killed=REQUIRED-count;
 for(int j=0;j<count;j++){
  int id=kind+j%3+6*(j/3),p=row[1+j];assert(floor_at(t,map,p) && p!=v.player && v.occ[p]<0);
  v.pos[id]=p;v.occ[p]=id;v.hp[id]=hp[id%6];v.energy[id]=70+v.w.rng.r(10);v.awake[id]=1;
 }
 assert(floor_at(t,map,row[7]));
 reveal(v,t);update_knowledge(v,c,t);observe(v,c,t,obs+i*OBS,mask+i*ACTIONS);
}
extern "C" int tactical_reset(State*s,int n,Config*c,Tables*t,const int*meta,const uint8_t*selected,float*obs,float*mask,void*stream){
 tactical_reset_kernel<<<(n+3)/4,4,0,(cudaStream_t)stream>>>(s,n,*c,*t,meta,selected,obs,mask);return cudaGetLastError();
}
