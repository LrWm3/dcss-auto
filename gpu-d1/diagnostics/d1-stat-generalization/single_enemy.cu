// Diagnostic-only extension. Production simulator and training are unchanged.
#include "hooks.cu"

HD void safe_distances(const State&s,const Tables&t,int enemy,uint16_t*ds,int radius=6) {
 for(int p=0;p<N;p++)ds[p]=65535;
 int16_t queue[N];int head=0,tail=1;queue[0]=s.player;ds[s.player]=0;
 while(head<tail){int p=queue[head++];for(int d=0;d<8;d++){
  int q=neighbor(p,d);
  if(q>=0&&s.viewed[q]&&floor_at(t,s.map_id,q)&&ds[q]==65535&&(enemy<0||cheb(q,enemy)>radius)){
   ds[q]=ds[p]+1;queue[tail++]=q;
  }
 }}
}
HD bool single_scene(State&s,Config c,const Tables&t,int profile,int hp,int enemy_kind,int adjacent){
 if(!make_scene(s,c,t,2,hp,profile))return false;
 int target=s.pos[0];s.hp[0]=0;s.occ[target]=-1;s.energy[0]=-30000;
 // All three exits are initially visible and reachable without waking the enemy.
 uint16_t ds[N];safe_distances(s,t,target,ds);int found=0;
 for(int distance=3;distance<=6&&found<3;distance++)for(int p=0;p<N&&found<3;p++)
  if(ds[p]==distance&&in_view(s,t,p))s.stairs[found++]=p;
 if(found<3){s.placement_clumped=-1;return false;}
 if(adjacent){const uint16_t*to_enemy=field(t,s.map_id,target);int best=-1,bestd=65535;
  for(int d=0;d<8;d++){int p=neighbor(s.player,d);if(floor_at(t,s.map_id,p)&&to_enemy[p]<bestd){best=p;bestd=to_enemy[p];}}
  if(best<0){s.placement_clumped=-1;return false;}target=best;
 }
 for(int i=0;i<ENEMIES;i++){s.enemy_slot[i]=-1;s.encountered[i]=0;}
 s.next_slot=0;s.pos[enemy_kind]=target;s.hp[enemy_kind]=s.max_hp[enemy_kind];s.energy[enemy_kind]=70;
 s.awake[enemy_kind]=adjacent;s.occ[target]=enemy_kind;
 s.first_stair_tick=-1;update_knowledge(s,episode_config(s,c),t);return true;
}
__global__ void single_scene_kernel(State*s,int n,Config c,Tables t,int profile,int hp,int kind,int adjacent,float*o,float*m){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n){single_scene(s[i],c,t,profile,hp,kind,adjacent);observe(s[i],c,t,o+i*OBS,m+i*ACTIONS);}
}
HD int single_controller(const State&s,Config c,const Tables&t,int mode){
 int enemy=-1;for(int j=0;j<s.active_count;j++)if(s.hp[j]>0)enemy=j;
 if(mode>=2||enemy<0){
  if(stair_index(s)>0)return 18;
  uint16_t ds[N];safe_distances(s,t,enemy<0?-1:s.pos[enemy],ds,mode==3?0:6);
  int target=-1,best=65535;for(int k=0;k<3;k++)if(ds[s.stairs[k]]<best){target=s.stairs[k];best=ds[target];}
  int d=route_first_step(s.player,target,ds);return d<0?16:d;
 }
 if(mode==1&&!s.awake[enemy]&&s.w.hp<s.player_max)return 17;
 if(cheb(s.player,s.pos[enemy])==1){for(int d=0;d<8;d++)if(neighbor(s.player,d)==s.pos[enemy])return 8+d;}
 if(s.awake[enemy])return 16;
 // Approach the visible sleeper; after waking, let it close before attacking.
 const uint16_t*ds=field(t,s.map_id,s.pos[enemy]);int best=ds[s.player],choice=-1;
 for(int d=0;d<8;d++){int p=neighbor(s.player,d);if(p>=0&&floor_at(t,s.map_id,p)&&ds[p]<best){best=ds[p];choice=d;}}
 return choice<0?16:choice;
}
// Returns exit/death/timeout, turns, kills, damage, return, HP on first attack,
// HP immediately after killing the enemy, and whether the enemy ever woke.
__global__ void single_rollout_kernel(State*s,int n,Config c,Tables t,int mode,float*result){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;float out[OUT],sum=0;int first=-1,killhp=-1,woke=0;
 for(int step=0;step<2048;step++){
  int action=single_controller(s[i],c,t,mode);
  if(action>=8&&action<16&&first<0)first=s[i].w.hp;
  for(int j=0;j<s[i].active_count;j++)woke|=s[i].hp[j]>0&&s[i].awake[j];
  transition(s[i],c,t,action,2048,out);sum+=out[0];
  if(action==17)assert(!out[1]&&out[36]&&s[i].w.hp==s[i].player_max);
  if(out[3]>0&&killhp<0)killhp=int(out[4]);
  if(out[1]){float*v=result+i*10;v[0]=out[2];v[1]=out[6];v[2]=out[7];v[3]=out[5];v[4]=out[3];v[5]=out[49];v[6]=sum;v[7]=first;v[8]=killhp;v[9]=woke;return;}
 }
 assert(false);
}
extern "C" {
int single_scene_api(State*s,int n,Config*c,Tables*t,int profile,int hp,int kind,int adjacent,float*o,float*m,void*stream){
 single_scene_kernel<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,n,*c,*t,profile,hp,kind,adjacent,o,m);return cudaGetLastError();
}
int single_rollout_api(State*s,int n,Config*c,Tables*t,int mode,float*out,void*stream){
 single_rollout_kernel<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,n,*c,*t,mode,out);return cudaGetLastError();
}
}
