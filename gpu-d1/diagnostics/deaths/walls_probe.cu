// Read-only analysis extension; original dynamics and observation code included unchanged.
#ifndef DEATHS_SIMULATOR
#define DEATHS_SIMULATOR "../../branches/vision15-curriculum-v1/src/learn.cu"
#endif
#include DEATHS_SIMULATOR
constexpr int D=24;
HD int empty_neighbors(const State &s,const Tables &t,int origin,int exclude=-1){
 int n=0;
 for(int a=0;a<8;a++){
  int p=neighbor(origin,a);
  if(p!=exclude && floor_at(t,s.map_id,p) && s.occ[p]<0)n++;
 }
 return n;
}
// Local geometry only: onward options exclude returning to the player's tile.
HD void geometry(const State &s,Config c,const Tables &t,int action,float*d){
 for(int k=12;k<D;k++)d[k]=0;
 int adj=0;
 for(int j=0;j<c.count;j++)if(s.hp[j]>0 && cheb(s.player,s.pos[j])==1)adj++;
 for(int a=0;a<8;a++){
  int p=neighbor(s.player,a);
  if(p<0){d[13]++;continue;}
  if(!s.viewed[p])d[15]++;
  if(!floor_at(t,s.map_id,p)){d[12]++;d[14]+=s.viewed[p]!=0;continue;}
  if(s.occ[p]>=0)continue;
  int nextadj=0;
  for(int j=0;j<c.count;j++)if(s.hp[j]>0 && cheb(p,s.pos[j])==1)nextadj++;
  int onward=empty_neighbors(s,t,p,s.player);
  d[16]+=onward>0;d[17]+=onward>0 && nextadj<adj;
  if(a==action){
   d[18]=nextadj<adj;d[19]=onward==0;
   d[20]=onward<empty_neighbors(s,t,s.player);
   d[21]=onward;
  }
 }
}

__global__ void diagnostic_step(State *s, int n, Config c, Tables t,
 const int64_t *actions, int limit, float *obs, float *mask, float *out,
 const bool *active, float *diag) {
 int i=blockIdx.x*blockDim.x+threadIdx.x; if(i>=n || !active[i]) return;
 State &v=s[i]; float *d=diag+i*D; for(int k=0;k<D;k++)d[k]=0;
 d[0]=v.w.hp; d[5]=v.killed;
 for(int j=0;j<c.count;j++) if(v.hp[j]>0){
  int dist=cheb(v.player,v.pos[j]);
  d[1]+=dist==1; d[2]+=dist<=3 && v.awake[j];
  d[3]+=in_view(v,t,v.pos[j]); d[4]+=v.awake[j]!=0;
 }
 int a=actions[i],dest=a<8?neighbor(v.player,a):v.player;
 // action class: wait=0, move=1, attack=2, blocked=3.
 d[8]=a==8?0:!floor_at(t,v.map_id,dest)?3:v.occ[dest]>=0?2:1;
 for(int a=0;a<8;a++){
  int p=neighbor(v.player,a); if(!floor_at(t,v.map_id,p)||v.occ[p]>=0)continue;
  d[9]++; int adjacent=0;
  for(int j=0;j<c.count;j++)if(v.hp[j]>0 && cheb(p,v.pos[j])==1)adjacent++;
  if(adjacent<d[1])d[10]++;
 }
 int postadj=0;
 if(d[8]==1)for(int j=0;j<c.count;j++)if(v.hp[j]>0 && cheb(dest,v.pos[j])==1)postadj++;
 d[11]=d[8]==1 && postadj>d[1];
 geometry(v,c,t,a,d);
 uint64_t damage=v.w.s.damage,attacks=v.w.s.attacks;
 transition(v,c,t,a,limit,out+i*OUT);
 d[6]=v.w.s.damage-damage; d[7]=v.w.s.attacks-attacks;
 observe(v,c,t,obs+i*OBS,mask+i*ACTIONS);
}
__global__ void fatal_probe(const State *before, int n, Config c, Tables t,
 const float *out, const float *mask, float *probe){
 int i=blockIdx.x*blockDim.x+threadIdx.x; if(i>=n || out[i*OUT+6]==0)return;
 for(int a=0;a<9;a++){
  probe[i*27+a]=-1; probe[i*27+9+a]=0; probe[i*27+18+a]=0; if(mask[i*ACTIONS+a]==0)continue;
  State trial=before[i]; float tmp[OUT]; transition(trial,c,t,a,2048,tmp);
  probe[i*27+a]=tmp[6]==0;
  int target=a<8?neighbor(before[i].player,a):-1;
  bool move=a<8 && floor_at(t,before[i].map_id,target) && before[i].occ[target]<0;
  probe[i*27+9+a]=move;
  int oldadj=0,newadj=0;
  for(int j=0;j<c.count;j++)if(before[i].hp[j]>0){
   oldadj+=cheb(before[i].player,before[i].pos[j])==1;
   if(move)newadj+=cheb(target,before[i].pos[j])==1;
  }
  probe[i*27+18+a]=move && newadj<oldadj;
 }
}
extern "C" int deaths_step(State *s,int n,Config*c,Tables*t,const int64_t*a,int limit,float*obs,float*mask,float*out,const bool*active,float*diag,void*stream){
 diagnostic_step<<<(n+3)/4,4,0,(cudaStream_t)stream>>>(s,n,*c,*t,a,limit,obs,mask,out,active,diag); return cudaGetLastError();
}
extern "C" int deaths_probe(const State*s,int n,Config*c,Tables*t,const float*out,const float*mask,float*probe,void*stream){
 fatal_probe<<<(n+3)/4,4,0,(cudaStream_t)stream>>>(s,n,*c,*t,out,mask,probe); return cudaGetLastError();
}

extern "C" int deaths_geometry_test(){
 uint8_t floor[N]; State s={}; Config c={}; Tables t={}; t.floor=floor;
 s.player=35*W+40;s.map_id=0;
 for(int p=0;p<N;p++){floor[p]=1;s.occ[p]=-1;s.viewed[p]=1;}
 float d[D]={};geometry(s,c,t,8,d);
 assert(d[12]==0 && empty_neighbors(s,t,s.player)==8 && d[16]==8);
 for(int p=0;p<N;p++)floor[p]=0;
 for(int x=30;x<50;x++)floor[35*W+x]=1;
 geometry(s,c,t,8,d);assert(d[12]==6 && empty_neighbors(s,t,s.player)==2 && d[16]==2);
 floor[s.player+1]=0;geometry(s,c,t,8,d);
 assert(d[12]==7 && empty_neighbors(s,t,s.player)==1 && d[16]==1);
 // Stepping into a one-cell spur provides no onward exit except backtracking.
 floor[s.player+1]=1;floor[s.player+2]=0;geometry(s,c,t,4,d);
 int spur=-1;for(int a=0;a<8;a++)if(neighbor(s.player,a)==s.player+1)spur=a;
 assert(spur>=0);geometry(s,c,t,spur,d);assert(d[19]==1);
 c.count=2;s.pos[0]=s.player-1;s.pos[1]=s.player+1;s.hp[0]=s.hp[1]=8;
 s.occ[s.pos[0]]=0;s.occ[s.pos[1]]=1;
 geometry(s,c,t,8,d);assert(d[12]==6 && empty_neighbors(s,t,s.player)==0 && d[16]==0);
 s.viewed[s.player-W]=0;geometry(s,c,t,8,d);assert(d[14]==5 && d[15]==1);
 return 0;
}
