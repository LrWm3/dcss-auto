#include "learn.cu"
#include <cstddef>
HD void metadata(const State&s,int64_t *v){
 v[0]=s.profile_id;v[1]=s.active_count;v[2]=s.w.hp;v[3]=s.player_max;v[4]=s.player_damage;v[5]=s.map_id;v[6]=s.player;
 for(int j=0;j<3;j++)v[7+j]=s.stairs[j];v[10]=s.ticks;v[11]=s.placement_clumped;
 v[12]=0;for(int j=0;j<ENEMIES;j++)v[12]+=s.hp[j]>0;
 v[13]=s.w.s.damage;v[14]=s.w.s.attacks;v[15]=s.w.s.blocks;v[16]=s.w.s.dodges;v[17]=s.w.episode;
}
__global__ void metadata_kernel(State*s,int n,int64_t*v){int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n)metadata(s[i],v+i*18);}
__global__ void reseed_kernel(State*s,int n,uint64_t seed){int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n)s[i].w.rng.seed(mix(seed+i),i+17);}
__global__ void observe_kernel(State*s,int n,Config c,Tables t,float*o,float*m){int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n)observe(s[i],c,t,o+i*OBS,m+i*ACTIONS);}
HD void restore_config(State&s,const Tables&t,int profile) {
 const int*v=t.profiles+profile*15;int old_max=s.player_max;
 s.profile_id=profile;s.player_max=v[0];s.player_damage=v[1];s.active_count=v[2];
 s.w.hp=mx(1,(s.w.hp*s.player_max+old_max/2)/old_max);
 for(int i=0;i<ENEMIES;i++) {
   int old=s.max_hp[i];s.max_hp[i]=i<s.active_count?v[3+i%6]:0;s.damage_cap[i]=i<s.active_count?v[9+i%6]:0;
   if(s.hp[i]>0 && i<s.active_count)s.hp[i]=mx(1,(s.hp[i]*s.max_hp[i]+mx(1,old)/2)/mx(1,old));
   if(i>=s.active_count){if(s.hp[i]>0)s.occ[s.pos[i]]=-1;s.hp[i]=0;s.energy[i]=-30000;}
 }
}
__global__ void restore_kernel(State*s,int n,Config c,Tables t,int profile,float*o,float*m){int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n){restore_config(s[i],t,profile);observe(s[i],c,t,o+i*OBS,m+i*ACTIONS);}}
HD bool make_scene(State &s, Config c,const Tables &t,int kind,int percent,int profile){
 restore_config(s,t,profile);c=episode_config(s,c);
 int player=-1,targets[3]={},number=kind==0?3:kind==1?2:1;
 for(int j=0;j<cell_count(t,s.map_id);j++) {
   int p=cells_map(t,s.map_id)[j];
   if(kind==0) {
     int east=neighbor(p,1);
     if(floor_at(t,s.map_id,east)&&!floor_at(t,s.map_id,neighbor(east,0))&&!floor_at(t,s.map_id,neighbor(east,2))&&floor_at(t,s.map_id,neighbor(p,3))&&floor_at(t,s.map_id,neighbor(p,6))&&floor_at(t,s.map_id,neighbor(p,7))) {
       player=p;targets[0]=neighbor(p,3);targets[1]=neighbor(p,6);targets[2]=neighbor(p,7);break;
     }
   } else if(kind==1) {
     if(floor_at(t,s.map_id,neighbor(p,0))&&floor_at(t,s.map_id,neighbor(p,1))){player=p;targets[0]=neighbor(p,0);targets[1]=neighbor(p,1);break;}
   } else {
     int previous=s.player;s.player=p;
     for(int d=0;d<8;d++) {int q=p;bool okay=true;for(int z=0;z<7;z++){q=neighbor(q,d);okay &= floor_at(t,s.map_id,q);}if(okay&&in_view(s,t,q)){player=p;targets[0]=q;break;}}
     s.player=previous;if(player>=0)break;
   }
 }
 if(player<0){s.placement_clumped=-1;return false;}
 for(int p=0;p<N;p++){s.occ[p]=-1;s.seen[p]=0;s.viewed[p]=0;s.frontier_slot[p]=-1;}
 s.frontier_count=s.floor_seen=s.next_slot=0;s.player=player;s.w.hp=mx(1,(s.player_max*percent+50)/100);s.w.regen=0;s.w.s={};s.ticks=s.killed=s.decisions=0;s.first_stair_tick=-1;
 for(int i=0;i<ENEMIES;i++){s.hp[i]=0;s.energy[i]=-30000;s.enemy_slot[i]=-1;s.encountered[i]=0;s.awake[i]=0;}
 for(int i=0;i<number;i++) {s.pos[i]=targets[i];s.hp[i]=s.max_hp[i];s.energy[i]=70;s.awake[i]=kind!=2;s.occ[s.pos[i]]=i;}
 if(kind==1){s.max_hp[0]*=2;s.hp[0]=s.max_hp[0];s.damage_cap[0]=1;s.max_hp[1]=mx(1,s.max_hp[1]/2);s.hp[1]=s.max_hp[1];s.damage_cap[1]*=2;}
 // Relocate stairs away from the diagnostic encounter, using no hidden policy cue.
 RNG stair;stair.seed(9981+s.map_id,73);
 for(int k=0;k<3;k++){int pick=-1,n=0;for(int j=0;j<cell_count(t,s.map_id);j++){int p=cells_map(t,s.map_id)[j];bool eligible=cheb(p,s.player)>=12 && s.occ[p]<0;for(int q=0;q<k;q++)eligible &= cheb(p,s.stairs[q])>=8;if(eligible&&stair.r(++n)==0)pick=p;}if(pick<0){s.placement_clumped=-1;return false;}s.stairs[k]=pick;}
 s.placement_clumped=0;reveal(s,t);update_knowledge(s,c,t);return true;
}
__global__ void scene_kernel(State*s,int n,Config c,Tables t,int kind,int percent,int profile,float*o,float*m){int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n){make_scene(s[i],c,t,kind,percent,profile);observe(s[i],c,t,o+i*OBS,m+i*ACTIONS);}}
extern "C" {
int stats_legacy_offset(){return offsetof(State,stairs);}
int stats_metadata(State*s,int n,int64_t*v,void*stream,int gpu){if(gpu){metadata_kernel<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,v);return cudaGetLastError();}for(int i=0;i<n;i++)metadata(s[i],v+i*18);return 0;}
int stats_reseed(State*s,int n,uint64_t seed,void*stream){reseed_kernel<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,seed);return cudaGetLastError();}
int stats_observe(State*s,int n,Config*c,Tables*t,float*o,float*m,void*stream,int gpu){if(gpu){observe_kernel<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,*c,*t,o,m);return cudaGetLastError();}for(int i=0;i<n;i++)observe(s[i],*c,*t,o+i*OBS,m+i*ACTIONS);return 0;}
int stats_restore_config(State*s,int n,Config*c,Tables*t,int profile,float*o,float*m,void*stream){restore_kernel<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,*c,*t,profile,o,m);return cudaGetLastError();}
int stats_scene(State*s,int n,Config*c,Tables*t,int kind,int percent,int profile,float*o,float*m,void*stream){scene_kernel<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,*c,*t,kind,percent,profile,o,m);return cudaGetLastError();}
int stats_semantics(Config*cfg,Tables*tbl) {
 Config c=*cfg;Tables t=*tbl;State s={};s.reset_rng.seed(411,11);s.parameter_rng.seed(411,13);reset(s,c,t);
 float o[OBS],q[OBS],m[ACTIONS],mm[ACTIONS],out[OUT];observe(s,c,t,o,m);
 for(int i=s.active_count;i<ENEMIES;i++){assert(s.hp[i]==0 && s.energy[i]<0);assert(s.occ[s.pos[i]]<0);}
 State copy=s;int hidden=-1;
 for(int i=0;i<s.active_count;i++)if(!in_view(s,t,s.pos[i])){hidden=i;break;}
 assert(hidden>=0);copy.hp[hidden]+=100;copy.max_hp[hidden]+=100;copy.damage_cap[hidden]+=100;
 observe(copy,c,t,q,mm);assert(!memcmp(o,q,sizeof(o))&&!memcmp(m,mm,sizeof(m)));
 // Remove all unseen enemies: neither total count nor hidden stats leak.
 for(int i=0;i<copy.active_count;i++)if(!in_view(copy,t,copy.pos[i])){copy.hp[i]=0;copy.occ[copy.pos[i]]=-1;}
 observe(copy,c,t,q,mm);assert(!memcmp(o,q,sizeof(o))&&!memcmp(m,mm,sizeof(m)));
 // Healing, deadline and all three descent choices with variable max HP.
 for(int i=0;i<ENEMIES;i++){s.hp[i]=0;s.energy[i]=-30000;}for(int p=0;p<N;p++)s.occ[p]=-1;
 s.w.hp=1;observe(s,c,t,o,m);assert(m[17]);transition(s,c,t,17,2048,out);
 assert(!out[1]&&s.w.hp==s.player_max&&out[26]>1);observe(s,c,t,o,m);assert(!m[17]);
 for(int k=0;k<3;k++){copy=s;copy.player=copy.stairs[k];observe(copy,c,t,o,m);assert(m[18]);transition(copy,c,t,18,2048,out);assert(out[2]&&out[44]==k+1&&out[26]==1);}
 s.ticks=2047;transition(s,c,t,16,2048,out);assert(out[7]&&out[5]==2048);
 return 0;
}
}
