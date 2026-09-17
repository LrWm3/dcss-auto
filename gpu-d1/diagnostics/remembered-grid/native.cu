// Exact production transitions/LOS, with experiment-owned reset and observations.
#define ANONYMOUS_POWER 1
#define EXTERNAL_EPISODE_RESET 1
#include "../d1-stat-generalization/learn.cu"
constexpr int GRID=32, GX=24, GY=19, CHANNELS=11, SCENE=264;
struct Memory { unsigned char visited[N]; int enemy, hp, damage, awake, stamp; };
HD int gridpos(int p){return (p/W-GY)*GRID+p%W-GX;}
HD void remember(State&s,Memory&m,const Tables&t){
 m.visited[s.player]=1;
 // Clear contradicted stale observations only when that square is observed.
 if(m.enemy>=0 && in_view(s,t,m.enemy) && (s.occ[m.enemy]<0 || s.hp[s.occ[m.enemy]]<=0))m.enemy=-1;
 for(int j=0;j<s.active_count;j++)if(s.hp[j]>0 && in_view(s,t,s.pos[j])){
  m.enemy=s.pos[j];m.hp=s.hp[j];m.damage=s.damage_cap[j];m.awake=s.awake[j];m.stamp=s.ticks;
 }
}
HD void setup(State&s,Memory&m,Config c,Tables t,const int*row,int world,uint64_t seed){
 s={};m={};m.enemy=-1;s.world_id=world;s.map_id=row[0];s.profile_id=0;s.player_max=18;s.player_damage=4;s.active_count=1;
 s.reset_rng.seed(mix(seed),11);s.parameter_rng.seed(mix(seed),13);s.w.rng.seed(mix(seed),17);s.w.hp=18;s.first_stair_tick=-1;
 s.player=row[8];for(int k=0;k<3;k++)s.stairs[k]=row[3+k];
 for(int p=0;p<N;p++){s.occ[p]=-1;s.frontier_slot[p]=-1;}
 for(int j=0;j<ENEMIES;j++){s.enemy_slot[j]=-1;s.energy[j]=-30000;}
 if(row[6]>=0){s.pos[0]=row[6];s.max_hp[0]=s.hp[0]=24;s.damage_cap[0]=20;s.energy[0]=70;s.occ[row[6]]=0;}
 reveal(s,t);update_knowledge(s,episode_config(s,c),t);remember(s,m,t);
 for(int j=1;j<row[7];j++){
  int a=-1;for(int d=0;d<8;d++)if(neighbor(s.player,d)==row[8+j])a=d;assert(a>=0);
  float o[OUT];transition(s,c,t,a,2048,o);assert(!o[1] && s.w.hp==18 && !s.awake[0]);remember(s,m,t);
 }
 assert(s.player==row[2]);
}
HD void export_grid(State&s,Memory&m,const Tables&t,unsigned char*g,float*mask,float*stats){
 memset(g,0,CHANNELS*GRID*GRID);
 for(int y=0;y<GRID;y++)for(int x=0;x<GRID;x++){
  int p=(y+GY)*W+x+GX,k=y*GRID+x;
  if(s.viewed[p])g[(floor_at(t,s.map_id,p)?0:1)*GRID*GRID+k]=255;
  g[2*GRID*GRID+k]=m.visited[p]*255;g[3*GRID*GRID+k]=in_view(s,t,p)*255;
  if(s.seen[p] && is_stair(s,p))g[4*GRID*GRID+k]=255;
 }
 int player=gridpos(s.player);assert(player>=0&&player<GRID*GRID);g[5*GRID*GRID+player]=255;
 if(m.enemy>=0){int k=gridpos(m.enemy);assert(k>=0&&k<GRID*GRID);
  g[6*GRID*GRID+k]=mn(255,m.hp*8);g[7*GRID*GRID+k]=mn(255,m.damage*12);
  g[8*GRID*GRID+k]=m.awake*255;g[9*GRID*GRID+k]=mn(255,s.ticks-m.stamp);g[10*GRID*GRID+k]=255;
 }
 for(int a=0;a<ACTIONS;a++)mask[a]=0;
 for(int d=0;d<8;d++){int p=neighbor(s.player,d);bool enemy=p>=0&&in_view(s,t,p)&&s.occ[p]>=0;
  mask[d]=p>=0&&(!s.viewed[p]||floor_at(t,s.map_id,p))&&!enemy;mask[8+d]=enemy;
 }
 mask[16]=1;mask[17]=s.w.hp<s.player_max&&!visible_awake(s,episode_config(s,Config{}),t);mask[18]=stair_index(s)>0;
 stats[0]=s.w.hp/18.f;stats[1]=s.ticks/2048.f;stats[2]=player%GRID;stats[3]=player/GRID;
}
// Observation-limited teacher. Distances are training labels only, never inputs.
HD int teacher(State&s,Memory&m,const Tables&t){
 if(stair_index(s))return 18;
 int16_t queue[N],ds[N],first[N];for(int p=0;p<N;p++)ds[p]=-1;
 int head=0,tail=1;queue[0]=s.player;ds[s.player]=0;first[s.player]=-1;
 int frontier=-1;bool threat=m.enemy>=0&&m.damage>=10;
 while(head<tail){int p=queue[head++];
  if(s.seen[p]&&is_stair(s,p))return first[p];
  if(frontier<0 && s.frontier_slot[p]>=0){for(int d=0;d<8;d++){int q=neighbor(p,d);if(q>=0&&!s.viewed[q]&&(!threat||cheb(q,m.enemy)>6)){frontier=p;break;}}}
  for(int d=0;d<8;d++){int q=neighbor(p,d);
   if(q<0||!s.viewed[q]||!floor_at(t,s.map_id,q)||ds[q]>=0)continue;
   if(threat&&cheb(q,m.enemy)<=6)continue;
   ds[q]=ds[p]+1;first[q]=p==s.player?d:first[p];queue[tail++]=q;
  }
 }
 if(frontier>=0){if(frontier!=s.player)return first[frontier];
  for(int d=0;d<8;d++){int q=neighbor(s.player,d);if(q>=0&&!s.viewed[q]&&(!threat||cheb(q,m.enemy)>6))return d;}
 }
 // A threatened anchor may have only forbidden unseen neighbors. Select an
 // actionable frontier, rather than oscillating toward that invalid anchor.
 int best=-1,bd=100000;
 for(int j=0;j<tail;j++){int p=queue[j];bool viable=false;
  for(int d=0;d<8;d++){int q=neighbor(p,d);if(q>=0&&!s.viewed[q]&&(!threat||cheb(q,m.enemy)>6))viable=true;}
  if(viable&&ds[p]<bd){best=p;bd=ds[p];}
 }
 if(best>=0&&best!=s.player)return first[best];
 for(int d=0;d<8;d++){int p=neighbor(s.player,d);if(p>=0&&in_view(s,t,p)&&s.occ[p]>=0)return 8+d;}
 return 16;
}
__global__ void init_custom(State*s,Memory*m,int n,Config c,Tables t,const int*scenes,const int*ids,uint64_t seed){int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n)setup(s[i],m[i],c,t,scenes+ids[i]*SCENE,i,seed+i);}
__global__ void export_custom(State*s,Memory*m,int n,Tables t,unsigned char*g,float*mask,float*stats,int64_t*labels,int*meta,int label){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 export_grid(s[i],m[i],t,g+i*CHANNELS*GRID*GRID,mask+i*ACTIONS,stats+i*4);
 if(label)labels[i]=teacher(s[i],m[i],t);
 int*z=meta+i*6;z[0]=s[i].player;z[1]=known_stairs(s[i]);z[2]=s[i].awake[0];z[3]=s[i].killed;z[4]=m[i].enemy;z[5]=s[i].ticks;
}
__global__ void step_custom(State*s,Memory*m,int n,Config c,Tables t,const int64_t*a,const bool*active,int limit,float*out){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n||!active[i])return;transition(s[i],c,t,a[i],limit,out+i*OUT);remember(s[i],m[i],t);
}
extern "C" {
int grid_memory_bytes(){return sizeof(Memory);}
int grid_init(State*s,Memory*m,int n,Config*c,Tables*t,const int*scenes,const int*ids,uint64_t seed,void*stream){init_custom<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,m,n,*c,*t,scenes,ids,seed);return cudaGetLastError();}
int grid_export(State*s,Memory*m,int n,Tables*t,unsigned char*g,float*mask,float*stats,int64_t*labels,int*meta,int label,void*stream){export_custom<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,m,n,*t,g,mask,stats,labels,meta,label);return cudaGetLastError();}
int grid_step(State*s,Memory*m,int n,Config*c,Tables*t,const int64_t*a,const bool*active,int limit,float*out,void*stream){step_custom<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,m,n,*c,*t,a,active,limit,out);return cudaGetLastError();}
}
// CPU parity/reference entry points, sharing every transition and memory update.
extern "C" {
int grid_cpu_init(State*s,Memory*m,int n,Config*c,Tables*t,const int*scenes,const int*ids,uint64_t seed){for(int i=0;i<n;i++)setup(s[i],m[i],*c,*t,scenes+ids[i]*SCENE,i,seed+i);return 0;}
int grid_cpu_export(State*s,Memory*m,int n,Tables*t,unsigned char*g,float*mask,float*stats,int64_t*labels){for(int i=0;i<n;i++){export_grid(s[i],m[i],*t,g+i*CHANNELS*GRID*GRID,mask+i*ACTIONS,stats+i*4);labels[i]=teacher(s[i],m[i],*t);}return 0;}
int grid_cpu_step(State*s,Memory*m,int n,Config*c,Tables*t,const int64_t*a,const bool*active,int limit,float*out){for(int i=0;i<n;i++)if(active[i]){transition(s[i],*c,*t,a[i],limit,out+i*OUT);remember(s[i],m[i],*t);}return 0;}
int grid_cpu_semantics(State*s,Memory*m,Tables*t){
 State q=*s;Memory mm=*m;unsigned char a[CHANNELS*GRID*GRID],b[CHANNELS*GRID*GRID];float am[ACTIONS],bm[ACTIONS],as[4],bs[4];
 export_grid(q,mm,*t,a,am,as);
 for(int p=0;p<N;p++)if(q.hp[0]>0&&!in_view(q,*t,q.pos[0])){q.hp[0]=0;q.occ[q.pos[0]]=-1;break;}
 for(int k=0;k<3;k++)if(!q.seen[q.stairs[k]]){for(int j=0;j<cell_count(*t,q.map_id);j++){int p=cells_map(*t,q.map_id)[j];if(!q.viewed[p]){q.stairs[k]=p;break;}}}
 export_grid(q,mm,*t,b,bm,bs);assert(!memcmp(a,b,sizeof(a))&&!memcmp(am,bm,sizeof(am))&&!memcmp(as,bs,sizeof(as)));
 for(int y=0;y<GRID;y++)for(int x=0;x<GRID;x++){int p=(GY+y)*W+GX+x,k=y*GRID+x;
  assert((a[k]!=0)==bool(s->viewed[p]&&floor_at(*t,s->map_id,p)));
  assert((a[GRID*GRID+k]!=0)==bool(s->viewed[p]&&!floor_at(*t,s->map_id,p)));
 }
 return 1;
}
}
