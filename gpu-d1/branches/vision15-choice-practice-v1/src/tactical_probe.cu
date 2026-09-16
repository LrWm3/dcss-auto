// Only custom initial states and diagnostic controllers; native mechanics unchanged.
#include "learn.cu"
// Metadata: player, first enemy, second enemy, task (0 target / 1 sleep), heldout.
__global__ void reset_choices(State*s,int n,Config c,Tables t,const int*meta,const uint8_t*selected,float*obs,float*mask){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n || (selected && !selected[i]))return;
 State&v=s[i];RNG rng=v.w.rng;int map=v.map_id,episode=v.w.episode;v={};v.w.rng=rng;v.w.episode=episode;v.map_id=map;
 const int*r=meta+map*5;v.player=r[0];v.ticks=256*v.w.rng.r(3);
 for(int p=0;p<N;p++){v.occ[p]=-1;v.frontier_slot[p]=-1;}
 for(int j=0;j<ENEMIES;j++){v.enemy_slot[j]=-1;v.energy[j]=-30000;}
 if(r[3]==0){
  v.w.hp=(r[4]?3:2)+2*v.w.rng.r(3);v.killed=REQUIRED-2;
  // Kind 0 versus more damaging kind 3; swap sides independently.
  int swap=v.w.rng.r(2),mode=v.w.rng.r(4);int weak_hp=mode==1?1:8,strong_hp=mode==2?1:(mode==3?8:16);
  if(mode==0)weak_hp=strong_hp=6;
  if(r[4]){weak_hp=weak_hp==8?7:weak_hp+1;strong_hp=strong_hp==16?15:(strong_hp==8?7:strong_hp+1);}
  for(int k=0;k<2;k++){int id=k?3:0,p=r[1+(k^swap)];v.pos[id]=p;v.occ[p]=id;v.hp[id]=k?strong_hp:weak_hp;v.awake[id]=1;v.energy[id]=70+v.w.rng.r(10);}
 }else{
  v.w.hp=v.w.rng.r(4)==0?18:(r[4]?2:1)+2*v.w.rng.r(2);v.killed=REQUIRED-1;
  int id=3,p=r[1];v.pos[id]=p;v.occ[p]=id;v.hp[id]=r[4]?28:32;v.energy[id]=-30000;v.awake[id]=0;
 }
 reveal(v,t);update_knowledge(v,c,t);
 // Both targets are visible. Vary their remembered discovery order independently
 // of side and type, so a fixed record index cannot identify the priority target.
 if(r[3]==0 && v.w.rng.r(2)){int slot=v.enemy_slot[0];v.enemy_slot[0]=v.enemy_slot[3];v.enemy_slot[3]=slot;}
 observe(v,c,t,obs+i*OBS,mask+i*ACTIONS);
}
extern "C" int tactical_reset(State*s,int n,Config*c,Tables*t,const int*meta,const uint8_t*selected,float*obs,float*mask,void*stream){reset_choices<<<(n+3)/4,4,0,(cudaStream_t)stream>>>(s,n,*c,*t,meta,selected,obs,mask);return cudaGetLastError();}
// Diagnostic modes: 0 focus weak; 1 focus dangerous; 2 lowest HP;
// 3 approach immediately then fight; 4 recover to full while asleep, then fight.
__global__ void choice_probe_kernel(State*s,int n,Config c,Tables t,int mode,int64_t*actions,float*stats){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;State&v=s[i];float*q=stats+i*12;
 for(int j=0;j<12;j++)q[j]=0;
 q[0]=v.w.hp;q[1]=v.hp[0];q[2]=v.hp[3];q[3]=v.hp[0];q[4]=v.awake[0]||v.awake[3];q[5]=v.ticks;q[6]=v.player;
 int chosen=-1,besthp=999,nearest=-1,bestdist=999;
 for(int id=0;id<c.count;id++)if(v.hp[id]>0){
  int dist=cheb(v.player,v.pos[id]);if(dist<bestdist){bestdist=dist;nearest=id;}
  if(dist==1 && v.hp[id]<besthp){besthp=v.hp[id];chosen=id;}
 }
 if(mode<2){int preferred=mode==0?0:3;if(v.hp[preferred]>0 && cheb(v.player,v.pos[preferred])==1)chosen=preferred;}
 int action=8;
 if(chosen>=0){for(int d=0;d<8;d++)if(neighbor(v.player,d)==v.pos[chosen]){action=d;break;}}
 else if(nearest>=0 && !(mode==4 && !v.awake[nearest] && v.w.hp<c.hp)){
  int best=bestdist;
  for(int d=0;d<8;d++){int p=neighbor(v.player,d);if(floor_at(t,v.map_id,p) && v.occ[p]<0 && cheb(p,v.pos[nearest])<best){best=cheb(p,v.pos[nearest]);action=d;}}
 }
 q[7]=bestdist;q[8]=v.hp[0]>0?cheb(v.player,v.pos[0]):-1;q[9]=v.hp[3]>0?cheb(v.player,v.pos[3]):-1;
 q[10]=v.hp[0]>0 && in_view(v,t,v.pos[0]);q[11]=nearest>=0 && in_view(v,t,v.pos[nearest]);
 actions[i]=action;
}
extern "C" int choice_probe(State*s,int n,Config*c,Tables*t,int mode,int64_t*actions,float*stats,void*stream){choice_probe_kernel<<<(n+3)/4,4,0,(cudaStream_t)stream>>>(s,n,*c,*t,mode,actions,stats);return cudaGetLastError();}
