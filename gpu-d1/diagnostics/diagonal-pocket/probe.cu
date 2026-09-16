// Diagnostic state construction only; combat, observations and actions unchanged.
#include "../../branches/vision15-clumps-v1/src/learn.cu"
HD int rotated(int x,int y,int r){for(int i=0;i<r;i++){int q=x;x=-y;y=q;}return (35+y)*W+40+x;}
__global__ void setup_test(State*s,int n,Config c,Tables t,uint64_t seed,float*obs,float*mask){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 int group=i/512, rotation=group%4, hp_index=(group/4)%3, kind=group/12==0?0:3;
 State &v=s[i];v={};v.map_id=rotation;v.w.rng.seed(mix(seed+i%512),i%512+1);
 v.w.hp=hp_index==0?6:hp_index==1?12:18;v.ticks=256;v.player=rotated(0,0,rotation);v.killed=18;
 for(int p=0;p<N;p++){v.occ[p]=-1;v.frontier_slot[p]=-1;}
 for(int j=0;j<ENEMIES;j++){v.enemy_slot[j]=-1;v.energy[j]=-30000;}
 const int mhp[6]={8,10,12,16,12,10};
 for(int j=0;j<6;j++){
  int id=kind+j%3+6*(j/3),p=rotated(j%3-1,-2-j/3,rotation);
  v.pos[id]=p;v.occ[p]=id;v.hp[id]=mhp[id%6];v.energy[id]=70+v.w.rng.r(10);v.awake[id]=1;
 }
 // Two-step diagonal retreat ends at a tile with only one walkable neighbor.
 int back=rotated(2,2,rotation),adjacent=0,exits=0;
 assert(floor_at(t,rotation,back));
 for(int j=0;j<c.count;j++)if(v.hp[j]>0)adjacent+=cheb(v.player,v.pos[j])==1;
 for(int a=0;a<8;a++)exits+=floor_at(t,rotation,neighbor(back,a));
 assert(adjacent==0 && exits==1);
 for(int k=1;k<=2;k++)assert(floor_at(t,rotation,rotated(k,k,rotation)));
 assert(!floor_at(t,rotation,rotated(1,2,rotation)) && !floor_at(t,rotation,rotated(2,1,rotation)));
 reveal(v,t);update_knowledge(v,c,t);observe(v,c,t,obs+i*OBS,mask+i*ACTIONS);
}
__global__ void control_action(const State*s,int n,Config c,int64_t*actions,bool retreat){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 int r=(i/512)%4;const State &v=s[i];int back=rotated(2,2,r);
 if(retreat && v.ticks<258){actions[i]=4+(1+r)%4;return;}
 int best=-1,hp=100000;
 for(int a=0;a<8;a++){int q=neighbor(v.player,a);if(q<0)continue;int id=v.occ[q];
  if(id>=0 && v.hp[id]>0 && v.hp[id]<hp){hp=v.hp[id];best=a;}}
 actions[i]=best<0?8:best;
}
extern "C" int hall_init(State*s,int n,Config*c,Tables*t,uint64_t seed,float*obs,float*mask,void*stream){
 setup_test<<<(n+3)/4,4,0,(cudaStream_t)stream>>>(s,n,*c,*t,seed,obs,mask);return cudaGetLastError();}
extern "C" int hall_control(State*s,int n,Config*c,int64_t*a,int retreat,void*stream){
 control_action<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,*c,a,retreat);return cudaGetLastError();}

__global__ void hall_measure(const State*s,int n,const int64_t*actions,int*out){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 int r=(i/512)%4;const State&v=s[i];int a=actions[i],q=a<8?neighbor(v.player,a):-1;
 out[i*2]=v.player==rotated(2,2,r);
 out[i*2+1]=q>=0 && v.occ[q]>=0;
}
extern "C" int hall_status(State*s,int n,int64_t*a,int*out,void*stream){
 hall_measure<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,a,out);return cudaGetLastError();
}
