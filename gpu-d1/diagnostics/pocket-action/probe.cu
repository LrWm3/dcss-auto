// Static native observation construction. No transition or enemy movement.
#include "../../branches/vision15-clumps-v1/src/learn.cu"
HD int position(int x,int y,int r){
 x-=POCKET_DISTANCE;y-=POCKET_DISTANCE;
 if(POCKET_MIRROR)x=-x;
 for(int j=0;j<r;j++){int old=x;x=-y;y=old;}
 return (35+y)*W+40+x;
}
__global__ void setup(State*s,int n,Config c,Tables t,float*obs,float*mask){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 int r=i%4,g=i/4,kind=g/9,hp_index=g/3%3,enemy_hp_index=g%3;
 State&v=s[i];v={};v.map_id=r;v.w.rng.seed(mix(900000),1);
 v.player=position(POCKET_DISTANCE,POCKET_DISTANCE,r);
 v.w.hp=hp_index==0?6:hp_index==1?12:18;v.ticks=256;v.killed=23;
 for(int p=0;p<N;p++){v.occ[p]=-1;v.frontier_slot[p]=-1;
  if(abs(p%W-40)<=16 && abs(p/W-35)<=16){v.viewed[p]=1;if(floor_at(t,r,p)){v.seen[p]=1;v.floor_seen++;}}
 }
 for(int j=0;j<ENEMIES;j++){v.enemy_slot[j]=-1;v.energy[j]=-30000;}
 const int hp[6]={8,10,12,16,12,10};
 int p=position(POCKET_DISTANCE-1,POCKET_DISTANCE-1,r);
 v.pos[kind]=p;v.occ[p]=kind;v.hp[kind]=enemy_hp_index==0?hp[kind]:enemy_hp_index==1?hp[kind]/2:1;
 v.awake[kind]=1;v.energy[kind]=75;
 assert(cheb(v.player,p)==1 && floor_at(t,r,p));
 reveal(v,t);update_knowledge(v,c,t);observe(v,c,t,obs+i*OBS,mask+i*ACTIONS);
}
extern "C" int pocket_init(State*s,int n,Config*c,Tables*t,float*obs,float*mask,void*stream){
 setup<<<(n+3)/4,4,0,(cudaStream_t)stream>>>(s,n,*c,*t,obs,mask);return cudaGetLastError();
}
