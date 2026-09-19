// Isolated experiment: full remembered terrain plus observation-only enemy records.
#define FULLSIZE_NAV 1
#include "native.cu"
struct ThreatMemory { Memory terrain; int pos[ENEMIES],hp[ENEMIES],maxhp[ENEMIES],damage[ENEMIES],awake[ENEMIES],stamp[ENEMIES]; };
HD void threat_clear(ThreatMemory&m){m={};m.terrain.enemy=-1;for(int j=0;j<ENEMIES;j++)m.pos[j]=-1;}
HD void threat_remember(State&s,ThreatMemory&m,const Tables&t){
 m.terrain.visited[s.player]=1;
 // Identity is used only to associate a currently observed enemy with its old
 // record. Unobserved movement, awakening, damage and death never update it.
 for(int j=0;j<ENEMIES;j++)if(m.pos[j]>=0&&in_view(s,t,m.pos[j])){
  int occupant=s.occ[m.pos[j]];
  if(occupant!=j||s.hp[j]<=0)m.pos[j]=-1;
 }
 for(int j=0;j<s.active_count;j++)if(s.hp[j]>0&&in_view(s,t,s.pos[j])){
  m.pos[j]=s.pos[j];m.hp[j]=s.hp[j];m.maxhp[j]=s.max_hp[j];m.damage[j]=s.damage_cap[j];m.awake[j]=s.awake[j];m.stamp[j]=s.ticks;
 }
}
HD void threat_export(State&s,ThreatMemory&m,Tables t,unsigned char*g,float*mask,float*stats){
 export_grid(s,m.terrain,t,g,mask,stats);
 memset(g+6*N,0,8*N);
 for(int j=0;j<ENEMIES;j++)if(m.pos[j]>=0){int p=m.pos[j];
  // A current observation takes precedence over an older record at that tile.
  if(g[11*N+p]&&g[10*N+p]<mn(255,s.ticks-m.stamp[j]))continue;
  g[6*N+p]=mn(255,m.hp[j]);g[7*N+p]=mn(255,m.maxhp[j]);g[8*N+p]=mn(255,m.damage[j]);
  g[9*N+p]=m.awake[j]*255;g[10*N+p]=mn(255,s.ticks-m.stamp[j]);g[11*N+p]=255;
  g[12*N+p]=(m.stamp[j]==s.ticks)*255;g[13*N+p]=(m.stamp[j]!=s.ticks)*255;
 }
 stats[0]=float(s.w.hp)/s.player_max;stats[4]=s.player_max;stats[5]=s.player_damage;stats[6]=s.w.hp;
}
__global__ void threat_init_kernel(State*s,ThreatMemory*m,int n,Config c,Tables t,uint64_t seed){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 s[i]={};s[i].world_id=i;s[i].reset_rng.seed(mix(seed+i),11);s[i].parameter_rng.seed(mix(seed+i),13);
 reset(s[i],c,t);threat_clear(m[i]);threat_remember(s[i],m[i],t);
}
__global__ void threat_export_kernel(State*s,ThreatMemory*m,int n,Tables t,unsigned char*g,float*mask,float*stats,int*meta){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 threat_export(s[i],m[i],t,g+i*14*N,mask+i*19,stats+i*7);
 int*z=meta+i*6;z[0]=s[i].player;z[1]=known_stairs(s[i]);z[2]=visible_awake(s[i],episode_config(s[i],Config{}),t);z[3]=s[i].killed;z[4]=s[i].profile_id;z[5]=s[i].ticks;
}
// One block per world: parallel terrain and zero fill, serial sparse records.
__global__ void threat_export_parallel(State*s,ThreatMemory*m,int n,Tables t,unsigned char*all,float*allmask,float*allstats,int*allmeta){
 int i=blockIdx.x;if(i>=n)return;State&q=s[i];ThreatMemory&mem=m[i];
 auto g=all+i*14*N;auto mask=allmask+i*19;auto stats=allstats+i*7;
 for(int k=threadIdx.x;k<14*N;k+=blockDim.x)g[k]=0;
 __syncthreads();
 for(int p=threadIdx.x;p<N;p+=blockDim.x){
  if(q.viewed[p])g[(floor_at(t,q.map_id,p)?0:1)*N+p]=255;
  g[2*N+p]=mem.terrain.visited[p]*255;g[3*N+p]=in_view(q,t,p)*255;
  if(q.seen[p]&&is_stair(q,p))g[4*N+p]=255;
 }
 if(threadIdx.x==0){
  g[5*N+q.player]=255;
  for(int j=0;j<ENEMIES;j++)if(mem.pos[j]>=0){int p=mem.pos[j];
   if(g[11*N+p]&&g[10*N+p]<mn(255,q.ticks-mem.stamp[j]))continue;
   g[6*N+p]=mn(255,mem.hp[j]);g[7*N+p]=mn(255,mem.maxhp[j]);g[8*N+p]=mn(255,mem.damage[j]);g[9*N+p]=mem.awake[j]*255;
   g[10*N+p]=mn(255,q.ticks-mem.stamp[j]);g[11*N+p]=255;g[12*N+p]=(mem.stamp[j]==q.ticks)*255;g[13*N+p]=(mem.stamp[j]!=q.ticks)*255;
  }
  for(int d=0;d<8;d++){int p=neighbor(q.player,d);bool enemy=p>=0&&in_view(q,t,p)&&q.occ[p]>=0;
   mask[d]=p>=0&&(!q.viewed[p]||floor_at(t,q.map_id,p))&&!enemy;mask[8+d]=enemy;
  }
  bool awake=visible_awake(q,episode_config(q,Config{}),t);
  mask[16]=1;mask[17]=q.w.hp<q.player_max&&!awake;mask[18]=stair_index(q)>0;
  stats[0]=float(q.w.hp)/q.player_max;stats[1]=q.ticks/2048.f;stats[2]=q.player%W;stats[3]=q.player/W;stats[4]=q.player_max;stats[5]=q.player_damage;stats[6]=q.w.hp;
  int*z=allmeta+i*6;z[0]=q.player;z[1]=known_stairs(q);z[2]=awake;z[3]=q.killed;z[4]=q.profile_id;z[5]=q.ticks;
 }
}
__global__ void threat_step_kernel(State*s,ThreatMemory*m,int n,Config c,Tables t,const int64_t*a,const bool*active,int limit,float*out){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n||!active[i])return;
 transition(s[i],c,t,a[i],limit,out+i*OUT);threat_remember(s[i],m[i],t);
}
// Scenario ABI matches existing remembered-grid fixtures, but accepts player and
// enemy stats explicitly. Histories are real physical steps, not injected maps.
__global__ void threat_scene_kernel(State*s,ThreatMemory*m,int n,Config c,Tables t,const int*rows,const int*ids,const int*power,uint64_t seed){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 setup(s[i],m[i].terrain,c,t,rows+ids[i]*SCENE,i,seed+i);
 // Existing setup uses the same 18/4 sleeper during the safe historical walk.
 // Evaluation stats change only at the end of that history, before decisions.
 const int*v=power+i*4;auto&q=s[i];q.player_max=v[0];q.player_damage=v[1];q.w.hp=v[0];
 if(q.hp[0]>0){q.hp[0]=q.max_hp[0]=v[2];q.damage_cap[0]=v[3];}
 Memory terrain=m[i].terrain;threat_clear(m[i]);m[i].terrain=terrain;m[i].terrain.enemy=-1;threat_remember(q,m[i],t);
}
extern "C" {
int threat_memory_bytes(){return sizeof(ThreatMemory);}
int threat_init(State*s,ThreatMemory*m,int n,Config*c,Tables*t,uint64_t seed,void*stream){threat_init_kernel<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,m,n,*c,*t,seed);return cudaGetLastError();}
int threat_export_reference(State*s,ThreatMemory*m,int n,Tables*t,unsigned char*g,float*mask,float*stats,int*meta,void*stream){threat_export_kernel<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,m,n,*t,g,mask,stats,meta);return cudaGetLastError();}
int threat_export(State*s,ThreatMemory*m,int n,Tables*t,unsigned char*g,float*mask,float*stats,int*meta,void*stream){threat_export_parallel<<<n,256,0,(cudaStream_t)stream>>>(s,m,n,*t,g,mask,stats,meta);return cudaGetLastError();}
int threat_step(State*s,ThreatMemory*m,int n,Config*c,Tables*t,const int64_t*a,const bool*active,int limit,float*out,void*stream){threat_step_kernel<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,m,n,*c,*t,a,active,limit,out);return cudaGetLastError();}
int threat_scene(State*s,ThreatMemory*m,int n,Config*c,Tables*t,const int*rows,const int*ids,const int*power,uint64_t seed,void*stream){threat_scene_kernel<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,m,n,*c,*t,rows,ids,power,seed);return cudaGetLastError();}
}

// Focused observation-boundary checks. Work on copies, never mutate a run.
__global__ void threat_check_kernel(State*s,ThreatMemory*m,Tables t,int*out){
 if(blockIdx.x||threadIdx.x)return;
 State q=s[0];ThreatMemory memory=m[0];
 int j=-1;for(int k=0;k<q.active_count;k++)if(memory.pos[k]>=0&&!in_view(q,t,memory.pos[k])){j=k;break;}
 assert(j>=0);int oldpos=memory.pos[j];auto before=memory;
 q.hp[j]=0;q.damage_cap[j]=1;q.awake[j]=!q.awake[j];q.occ[q.pos[j]]=-1;q.pos[j]=0;
 threat_remember(q,memory,t);
 for(unsigned k=0;k<sizeof(memory);k++)assert(((unsigned char*)&before)[k]==((unsigned char*)&memory)[k]);out[0]=1;
 // A hidden death must not remove a remembered threat. Only re-observation does.
 q.player=oldpos;threat_remember(q,memory,t);assert(memory.pos[j]==-1);out[1]=1;
 q=s[0];memory=m[0];q.player=oldpos;q.hp[j]=7;q.damage_cap[j]=9;q.awake[j]=1;q.occ[oldpos]=j;q.pos[j]=oldpos;q.ticks+=3;
 threat_remember(q,memory,t);assert(memory.hp[j]==7&&memory.damage[j]==9&&memory.awake[j]==1&&memory.stamp[j]==q.ticks);out[2]=1;
 // Recognizing a visible enemy at a new location removes its previous marker.
 int next=-1;for(int d=0;d<8;d++){int p=neighbor(oldpos,d);if(p>=0&&floor_at(t,q.map_id,p)&&in_view(q,t,p)){next=p;break;}}
 assert(next>=0);q.occ[oldpos]=-1;q.pos[j]=next;q.occ[next]=j;threat_remember(q,memory,t);assert(memory.pos[j]==next);out[3]=1;
 int k=j==0?1:0;q.active_count=mx(q.active_count,k+1);q.pos[k]=oldpos;q.occ[oldpos]=k;q.hp[k]=q.max_hp[k]=6;q.damage_cap[k]=4;
 threat_remember(q,memory,t);assert(memory.pos[j]==next&&memory.pos[k]==oldpos);out[4]=1;
 threat_clear(memory);for(int z=0;z<ENEMIES;z++)assert(memory.pos[z]==-1);out[5]=1;
}
extern "C" int threat_checks(State*s,ThreatMemory*m,Tables*t,int*out,void*stream){threat_check_kernel<<<1,1,0,(cudaStream_t)stream>>>(s,m,*t,out);return cudaGetLastError();}

__global__ void threat_reset_done_kernel(State*s,ThreatMemory*m,int n,Config c,Tables t,bool*active){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n||active[i])return;
 reset(s[i],c,t);threat_clear(m[i]);threat_remember(s[i],m[i],t);active[i]=true;
}
extern "C" int threat_reset_done(State*s,ThreatMemory*m,int n,Config*c,Tables*t,bool*active,void*stream){threat_reset_done_kernel<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,m,n,*c,*t,active);return cudaGetLastError();}
