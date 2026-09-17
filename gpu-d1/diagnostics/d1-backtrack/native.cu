#include "../d1-sleeper-bypass/native.cu"
HD int coord(int x,int y,int g){if(g>=4)x=-x;for(int i=0;i<g%4;i++){int q=x;x=-y;y=q;}return (35+y)*W+40+x;}
HD int direction_to(int p,int q){for(int d=0;d<8;d++)if(neighbor(p,d)==q)return d;return -1;}
__global__ void setup_backtrack(State*s,int n,Config c,Tables t,int reps,uint64_t seed,float*obs,float*mask,int*checks,bool stairs_known){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 int condition=i/reps,map=condition/3,kind=condition%3,g=map%8;const int lengths[4]={4,8,16,24};int length=lengths[map/8];
 State&v=s[i];v={};v.world_id=i;v.map_id=map;v.profile_id=4;v.player_max=18;v.player_damage=4;v.active_count=24;
 v.reset_rng.seed(mix(seed+i),11);v.parameter_rng.seed(mix(seed+i),13);v.w.rng.seed(mix(seed+i%reps),i%reps+17);
 v.w.hp=18;v.player=coord(-length,stairs_known?-12:0,g);v.first_stair_tick=-1;
 for(int p=0;p<N;p++){v.occ[p]=-1;v.frontier_slot[p]=-1;}
 for(int j=0;j<ENEMIES;j++){v.enemy_slot[j]=-1;v.energy[j]=-30000;}
 for(int k=0;k<3;k++)v.stairs[k]=coord(-length,-12-4*k,g);
 v.pos[0]=coord(7,0,g);v.max_hp[0]=v.hp[0]=kind==0?0:kind==1?6:24;v.damage_cap[0]=kind==2?20:4;v.energy[0]=70;
 if(kind)v.occ[v.pos[0]]=0;
 reveal(v,t);update_knowledge(v,episode_config(v,c),t);
 float out[OUT];
 // A real preceding walk reveals a connected route to two stairs. No map data
 // is injected into observations, and the extra 12 physical turns are charged.
 if(stairs_known){
  v.first_stair_tick=0;
  for(int y=-12;y<0;y++){
   int a=direction_to(v.player,coord(-length,y+1,g));assert(a>=0);
   transition(v,c,t,a,2048,out);assert(!out[1]&&v.w.hp==18&&!v.awake[0]);
  }
 }
 for(int x=-length;x<0;x++){
  int a=direction_to(v.player,coord(x+1,0,g));assert(a>=0);transition(v,c,t,a,2048,out);assert(!out[1]&&v.w.hp==18&&!v.awake[0]);
 }
 observe(v,c,t,obs+i*OBS,mask+i*ACTIONS);
 assert(v.player==coord(0,0,g)&&known_stairs(v)==(stairs_known?2:0)&&!v.viewed[coord(14,0,g)]);
 assert(!kind||in_view(v,t,v.pos[0]));
 uint16_t ds[N];known_distances(v,t,ds,true);int target=nearest(v,ds),forward=direction_to(v.player,coord(1,0,g));
 assert(target>=0);int d=route_first_step(v.player,target,ds);checks[i*4]=d==forward;checks[i*4+1]=ds[target];
 // Oracle verification: a shortest known-safe full-map route exists to stairs.
 bypass_distances(v,t,v.pos[0],false,ds);assert(ds[v.stairs[0]]<65535);
 checks[i*4+2]=ds[v.stairs[0]];checks[i*4+3]=known_stairs(v);
}
__global__ void backtrack_measure(State*s,int n,int reps,int*out){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;State&v=s[i];int map=(i/reps)/3,g=map%8;const int lengths[4]={4,8,16,24};int length=lengths[map/8];
 int player=v.player;int x=player%W-40,y=player/W-35;
 for(int j=0;j<(4-g%4)%4;j++){int q=x;x=-y;y=q;}if(g>=4)x=-x;
 out[i*5]=x;out[i*5+1]=y;out[i*5+2]=v.awake[0];out[i*5+3]=known_stairs(v);out[i*5+4]=v.killed;
}
extern "C" {
int backtrack_setup(State*s,int n,Config*c,Tables*t,int reps,uint64_t seed,float*o,float*m,int*checks,void*stream){setup_backtrack<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,n,*c,*t,reps,seed,o,m,checks,false);return cudaGetLastError();}
int backtrack_setup_known(State*s,int n,Config*c,Tables*t,int reps,uint64_t seed,float*o,float*m,int*checks,void*stream){setup_backtrack<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,n,*c,*t,reps,seed,o,m,checks,true);return cudaGetLastError();}
int backtrack_measure_api(State*s,int n,int reps,int*out,void*stream){backtrack_measure<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,reps,out);return cudaGetLastError();}
}
