// Read-only audit against independent full-memory/frontier reconstruction.
#include "../../branches/vision-v1/src/learn.cu"
extern "C" int audit(const learn::State *states, int n, const learn::Tables *tp,
                     const float *obs, int los_on, int *errors) {
 using namespace learn; const Tables &t=*tp;
 for(int i=0;i<n;i++) {
  const State &s=states[i]; const float *o=obs+i*OBS;
  const uint8_t *floor=t.floor+s.map_id*N;
  bool expected[N]={}; int count=0;
  for(int p=0;p<N;p++) {
   if(s.seen[p] != bool(s.viewed[p] && floor[p])) errors[0]++;
   count+=s.seen[p]!=0;
   if(s.seen[p]) for(int d=0;d<8;d++) {
    int q=neighbor(p,d); if(q>=0 && !s.viewed[q]) expected[p]=true;
   }
   int slot=s.frontier_slot[p];
   bool actual=slot>=0 && slot<s.frontier_count && s.frontier_cells[slot]==p;
   if(actual!=expected[p]) errors[1]++;
  }
  if(count!=s.floor_seen) errors[2]++;
  for(int k=0;k<s.frontier_count;k++) {
   int p=s.frontier_cells[k]; if(p<0 || p>=N || !expected[p] || s.frontier_slot[p]!=k) errors[3]++;
  }
  for(int dy=-4;dy<=4;dy++) for(int dx=-4;dx<=4;dx++) {
   int x=s.player%W+dx,y=s.player/W+dy,j=(dy+4)*9+dx+4;
   if(x<0 || x>=W || y<0 || y>=H) continue;
   int p=y*W+x,b=(dy+8)*17+dx+8;
   bool v=!los_on || ((t.los[(size_t(s.map_id)*N+s.player)*10+b/32]>>(b%32))&1);
   if(v && !s.viewed[p]) errors[4]++;
   if(o[OBS-81+j]!=v || o[j]!=(s.viewed[p] ? (floor[p] ? 1.f : -1.f):0.f)) errors[5]++;
  }
  // Full BFS, without incremental frontiers or early stopping.
  uint16_t ds[N]; int queue[N]; for(int p=0;p<N;p++) ds[p]=65535;
  int head=0,tail=1;queue[0]=s.player;ds[s.player]=0;
  while(head<tail) {
   int p=queue[head++];
   for(int d=0;d<8;d++) {
    int q=neighbor(p,d);
    if(q>=0 && s.viewed[q] && floor[q] && ds[q]==65535) {
     ds[q]=ds[p]+1;queue[tail++]=q;
    }
   }
  }
  int target=-1,distance=65535;
  for(int k=0;k<s.frontier_count;k++) {
   int p=s.frontier_cells[k];if(ds[p]<distance) {target=p;distance=ds[p];}
  }
  const int b=BASE_OBS+40;
  if(o[b]!=(target>=0)) errors[6]++;
  if(target>=0) {
   if(abs(o[b+1]-(target%W-s.player%W)/float(W))>1e-6f ||
      abs(o[b+2]-(target/W-s.player/W)/float(H))>1e-6f ||
      abs(o[b+3]-distance/float(W+H))>1e-6f) errors[7]++;
   int direction=route_first_step(s.player,target,ds);
   for(int d=0;d<8;d++) if(o[b+7+d]!=(direction==d)) errors[8]++;
   if(target==s.player) errors[9]++;
  }
 }
 return 0;
}
