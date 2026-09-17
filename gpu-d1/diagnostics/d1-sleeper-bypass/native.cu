// Isolated diagnostics/reset curriculum; production transition is unchanged.
#include "../d1-anonymous-power/native.cu"
HD bool wakes_at(const Tables&t,int map,int enemy,int player){
 int dx=player%W-enemy%W,dy=player/W-enemy/W;
 if(abs(dx)>6||abs(dy)>6)return false;
 int bit=(dy+8)*17+dx+8;
 return (t.los[(size_t(map)*N+enemy)*10+bit/32]>>(bit%32))&1;
}
HD void bypass_distances(const State&s,const Tables&t,int enemy,bool known,uint16_t*ds){
 int16_t queue[N];for(int p=0;p<N;p++)ds[p]=65535;
 int head=0,tail=1;queue[0]=s.player;ds[s.player]=0;
 while(head<tail){int p=queue[head++];for(int d=0;d<8;d++){
  int q=neighbor(p,d);if(q>=0&&floor_at(t,s.map_id,q)&&(!known||s.viewed[q])&&ds[q]==65535&&q!=enemy&&!wakes_at(t,s.map_id,enemy,q)){
   ds[q]=ds[p]+1;queue[tail++]=q;
  }
 }}
}
HD int nearest(const State&s,const uint16_t*ds){int target=-1,best=65535;
 for(int k=0;k<s.frontier_count;k++){int p=s.frontier_cells[k];if(ds[p]<best){best=ds[p];target=p;}}return target;
}
HD bool route_wakes(const State&s,const Tables&t,int enemy,int target,const uint16_t*ds){
 if(target<0||ds[target]==65535)return false;
 int p=target;while(p!=s.player){if(wakes_at(t,s.map_id,enemy,p)||p==enemy)return true;
  int prev=-1;for(int d=0;d<8;d++){int q=neighbor(p,d);if(q>=0&&int(ds[q])+1==ds[p]){prev=q;break;}}
  if(prev<0)break;p=prev;
 }return false;
}
HD bool bypass_scene(State&s,Config c,const Tables&t){
 if(known_stairs(s))return false;
 uint16_t ds[N],safe[N];known_distances(s,t,ds,true);int target=nearest(s,ds);
 if(target<0||target==s.player)return false;
 int enemy=-1,offset=s.parameter_rng.r(cell_count(t,s.map_id));
 for(int j=0;j<cell_count(t,s.map_id);j++){
  int p=cells_map(t,s.map_id)[(j+offset)%cell_count(t,s.map_id)];
  if(cheb(p,s.player)!=7||!in_view(s,t,p)||is_stair(s,p)||!route_wakes(s,t,p,target,ds))continue;
  bypass_distances(s,t,p,true,safe);int alternative=nearest(s,safe);
  if(alternative<0||alternative==s.player||route_first_step(s.player,alternative,safe)<0)continue;
  bypass_distances(s,t,p,false,safe);bool exit=false;
  for(int k=0;k<3;k++)exit|=safe[s.stairs[k]]<65535&&!s.seen[s.stairs[k]];
  if(exit){enemy=p;break;}
 }
 if(enemy<0)return false;
 for(int p=0;p<N;p++)s.occ[p]=-1;
 for(int i=0;i<ENEMIES;i++){s.hp[i]=0;s.energy[i]=-30000;s.enemy_slot[i]=-1;s.encountered[i]=0;s.awake[i]=0;}
 const int*v=t.profiles+s.profile_id*15;int kind=s.parameter_rng.r(6);
 s.pos[0]=enemy;s.max_hp[0]=s.hp[0]=v[3+kind];s.damage_cap[0]=v[9+kind];s.energy[0]=70;s.occ[enemy]=0;
 s.next_slot=0;s.w.hp=s.parameter_rng.r(2)?s.player_max:mx(1,s.player_max/2);s.placement_clumped=2;
 update_knowledge(s,episode_config(s,c),t);return true;
}
__global__ void inject_kernel(State*s,int n,Config c,Tables t,float*o,float*m,const float*out,int*tags,int initial,int percent){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n||(!initial&&!out[i*OUT+1]))return;
 tags[i]=0;
 // Separate selection stream: control and curriculum do not consume combat RNG.
 if(percent>0&&mix(uint64_t(s[i].world_id)+uint64_t(s[i].w.episode)*9137+812981)%100<unsigned(percent)){
  tags[i]=bypass_scene(s[i],c,t);observe(s[i],c,t,o+i*OBS,m+i*ACTIONS);
 }
}
// Header followed by known-map codes: 0 unknown, 1 floor, -1 wall.
__global__ void inspect_kernel(State*s,int n,Tables t,int*out){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;State&v=s[i];int*z=out+i*(32+N);
 for(int j=0;j<32+N;j++)z[j]=0;
 uint16_t ds[N],safe[N];known_distances(v,t,ds,true);int target=nearest(v,ds),enemy=-1;
 for(int j=0;j<v.active_count;j++)if(v.hp[j]>0&&!v.awake[j]&&in_view(v,t,v.pos[j])){enemy=v.pos[j];break;}
 z[0]=v.player;z[1]=enemy;z[2]=target;z[3]=target<0?-1:ds[target];z[4]=route_first_step(v.player,target,ds);z[5]=v.frontier_count;z[6]=v.map_id;
 if(enemy>=0){z[7]=route_wakes(v,t,enemy,target,ds);bypass_distances(v,t,enemy,true,safe);int alt=nearest(v,safe);
  z[8]=alt;z[9]=alt<0?-1:safe[alt];z[10]=route_first_step(v.player,alt,safe);
  bypass_distances(v,t,enemy,false,safe);for(int k=0;k<3;k++)z[11]+=safe[v.stairs[k]]<65535;
 }
 for(int d=0;d<8;d++){int p=neighbor(v.player,d);z[12+d]=(p>=0&&(!v.viewed[p]||floor_at(t,v.map_id,p))&&v.occ[p]<0);z[20+d]=enemy>=0&&p>=0&&wakes_at(t,v.map_id,enemy,p);}
 for(int p=0;p<N;p++)z[32+p]=v.viewed[p]?(floor_at(t,v.map_id,p)?1:-1):0;
}
extern "C" {
int bypass_inject(State*s,int n,Config*c,Tables*t,float*o,float*m,float*out,int*tags,int initial,int percent,void*stream){
 inject_kernel<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,n,*c,*t,o,m,out,tags,initial,percent);return cudaGetLastError();}
int bypass_inspect(State*s,int n,Tables*t,int*out,void*stream){inspect_kernel<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,n,*t,out);return cudaGetLastError();}
}

__global__ void verify_kernel(State*s,int n,Config c,Tables t,const int*tags,int*out){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n||!tags[i])return;
 State&v=s[i];int enemy=v.pos[0];uint16_t ds[N];float step[OUT];
 for(int tick=0;tick<2048;tick++){
  bypass_distances(v,t,enemy,false,ds);int target=-1,best=65535;
  for(int k=0;k<3;k++)if(ds[v.stairs[k]]<best){target=v.stairs[k];best=ds[target];}
  assert(target>=0&&!v.awake[0]);int a=stair_index(v)>0?18:route_first_step(v.player,target,ds);assert(a>=0);
  transition(v,c,t,a,2048,step);
  if(step[1]){assert(step[2]&&step[3]==0&&step[49]==0);out[i]=1;return;}
 }
 assert(false);
}
extern "C" int bypass_verify(State*s,int n,Config*c,Tables*t,int*tags,int*out,void*stream){
 verify_kernel<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(s,n,*c,*t,tags,out);return cudaGetLastError();
}
