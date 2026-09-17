#include "native.cu"
__global__ void setup_beyond(State*s,int n,Config c,Tables t,int reps,uint64_t seed,float*obs,float*mask,int*checks,bool strong_awake){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 int condition=i/reps,map=condition/3,kind=condition%3,g=map%8;const int distances[4]={4,8,16,24};int end=7+distances[map/8];
 State&v=s[i];v={};v.world_id=i;v.map_id=map;v.profile_id=4;v.player_max=18;v.player_damage=4;v.active_count=24;
 v.reset_rng.seed(mix(seed+i),11);v.parameter_rng.seed(mix(seed+i),13);v.w.rng.seed(mix(seed+i%reps),i%reps+17);
 v.w.hp=18;v.player=coord(-8,0,g);v.first_stair_tick=-1;
 for(int p=0;p<N;p++){v.occ[p]=-1;v.frontier_slot[p]=-1;}
 for(int j=0;j<ENEMIES;j++){v.enemy_slot[j]=-1;v.energy[j]=-30000;}
 for(int k=0;k<3;k++)v.stairs[k]=coord(end,-k,g);
 reveal(v,t);update_knowledge(v,episode_config(v,c),t);
 // Establish remembered route before introducing the encounter. This is an
 // explicit synthetic intervention, not a claim one can cross this sleeper safely.
 float out[OUT];
 for(int x=-8;x<end;x++){transition(v,c,t,direction_to(v.player,coord(x+1,0,g)),2048,out);assert(!out[1]);}
 for(int x=end;x>0;x--){transition(v,c,t,direction_to(v.player,coord(x-1,0,g)),2048,out);assert(!out[1]);}
 v.pos[0]=coord(7,0,g);v.max_hp[0]=v.hp[0]=kind==0?0:kind==1?6:24;v.damage_cap[0]=kind==2?20:4;v.energy[0]=70;
 if(kind)v.occ[v.pos[0]]=0;
 v.awake[0]=strong_awake&&kind==2;
 update_knowledge(v,episode_config(v,c),t);observe(v,c,t,obs+i*OBS,mask+i*ACTIONS);
 assert(v.player==coord(0,0,g)&&known_stairs(v)==3&&v.w.hp==18&&bool(v.awake[0])==(strong_awake&&kind==2));
 assert(!kind||in_view(v,t,v.pos[0]));assert(!v.viewed[coord(end,12,g)]);
 int forward=direction_to(v.player,coord(1,0,g));
 assert(obs[i*OBS+FRONTIER_OBS+7+forward]==1&&obs[i*OBS+STAIR_OBS+7+forward]==1);
 checks[i*4]=1;checks[i*4+1]=v.ticks;checks[i*4+2]=end;checks[i*4+3]=known_stairs(v);
}
extern "C" int beyond_setup(State*s,int n,Config*c,Tables*t,int reps,uint64_t seed,float*o,float*m,int*checks,void*stream){setup_beyond<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,n,*c,*t,reps,seed,o,m,checks,false);return cudaGetLastError();}

extern "C" int beyond_setup_awake(State*s,int n,Config*c,Tables*t,int reps,uint64_t seed,float*o,float*m,int*checks,void*stream){setup_beyond<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,n,*c,*t,reps,seed,o,m,checks,true);return cudaGetLastError();}
