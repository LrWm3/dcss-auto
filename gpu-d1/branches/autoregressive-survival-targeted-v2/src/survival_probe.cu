// Only episode initialization and diagnostics; native observation/combat unchanged.
#include "learn.cu"
// Metadata stride 10: player, goal, six enemy positions, family, orientation.
__global__ void survival_reset_kernel(State*s,int n,Config c,Tables t,const int*meta,const uint8_t*selected,float*obs,float*mask){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n || (selected && !selected[i]))return;
 State &v=s[i];RNG rng=v.w.rng;int map=v.map_id,episode=v.w.episode;v={};v.w.rng=rng;v.w.episode=episode;v.map_id=map;
 const int*r=meta+map*10;v.player=r[0];v.w.hp=6+6*v.w.rng.r(3);
 for(int p=0;p<N;p++){
  v.occ[p]=-1;v.frontier_slot[p]=-1;
  // Previously explored local terrain; padding is unknown and unreachable.
  if(abs(p%W-40)<18 && abs(p/W-35)<18){v.viewed[p]=1;if(floor_at(t,map,p)){v.seen[p]=1;v.floor_seen++;}}
 }
 for(int j=0;j<ENEMIES;j++){v.enemy_slot[j]=-1;v.energy[j]=-30000;}
 bool easy=v.w.rng.r(5)==0;int count=easy?1:6,base=easy?0:(v.w.rng.r(4)==0?0:3);v.killed=REQUIRED-count;
 const int hp[6]={8,10,12,16,12,10};
 for(int j=0;j<count;j++){
  int id=base+j%3+6*(j/3),p=r[2+j];assert(floor_at(t,map,p) && p!=v.player);
  v.pos[id]=p;v.occ[p]=id;v.hp[id]=hp[id%6];v.awake[id]=1;v.energy[id]=70+v.w.rng.r(10);
 }
 assert(floor_at(t,map,r[1]));reveal(v,t);update_knowledge(v,c,t);observe(v,c,t,obs+i*OBS,mask+i*ACTIONS);
}
extern "C" int tactical_reset(State*s,int n,Config*c,Tables*t,const int*meta,const uint8_t*selected,float*obs,float*mask,void*stream){survival_reset_kernel<<<(n+3)/4,4,0,(cudaStream_t)stream>>>(s,n,*c,*t,meta,selected,obs,mask);return cudaGetLastError();}

__global__ void survival_probe_kernel(State*s,int n,Config c,Tables t,const int*meta,int mode,int64_t*actions,float*stats){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;State&v=s[i];const int*r=meta+10*v.map_id;int goal=r[1];
 int adjacent=0,visible=0,alive=0;
 for(int j=0;j<c.count;j++)if(v.hp[j]>0){alive++;adjacent+=cheb(v.player,v.pos[j])==1;visible+=in_view(v,t,v.pos[j])&&v.awake[j];}
 float*q=stats+i*8;q[0]=v.w.hp;q[1]=v.player;q[2]=adjacent;q[3]=visible;q[4]=v.ticks;q[5]=v.player==goal;q[6]=alive;q[7]=r[8];
 int attack=adjacent_attack(v,c,t),action=attack>=0?8+attack:16;
 if(mode==0)action=heuristic(v,c,t);
 if(mode==1 && v.player!=goal){
  const uint16_t*ds=field(t,v.map_id,goal);int best=-1,score=100000;
  for(int d=0;d<8;d++){
   int p=neighbor(v.player,d);if(p<0||!floor_at(t,v.map_id,p)||v.occ[p]>=0||ds[p]>=ds[v.player])continue;
   int exposure=0;for(int j=0;j<c.count;j++)if(v.hp[j]>0 && in_view(v,t,v.pos[j]))exposure+=cheb(p,v.pos[j])==1;
   int value=10*ds[p]+3*exposure;if(value<score){score=value;best=d;}
  }
  if(best>=0)action=best;
 }
 actions[i]=action;
}
extern "C" int tactical_probe(State*s,int n,Config*c,Tables*t,const int*meta,int mode,int64_t*a,float*out,void*stream){survival_probe_kernel<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,*c,*t,meta,mode,a,out);return cudaGetLastError();}
