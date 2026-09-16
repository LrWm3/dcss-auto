// Read-only analysis extension; original dynamics and observation code included unchanged.
#include "../../branches/vision15-curriculum-v1/src/learn.cu"
constexpr int D=16;
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
