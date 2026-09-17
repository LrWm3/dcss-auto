#define ANONYMOUS_POWER 1
#include "../d1-stat-generalization/single_enemy.cu"

// Exact adjacent, awake, speed-10 fight: player acts first, then one enemy
// attack if it survived. Calls the production armor/shield/evasion routine.
HD void duel(Config c,const int*v,uint64_t seed,float*out){
 c.hp=v[0];c.kinds[0]={10,v[3],19,15};World w={};w.hp=mx(1,(v[0]*v[4]+50)/100);w.rng.seed(mix(seed),17);
 int enemy=v[2];
 for(int tick=1;tick<=2048;tick++){
  w.blocks=0;w.regen+=c.regen;while(w.regen>=100){w.hp=mn(c.hp,w.hp+1);w.regen-=100;}
  if(w.rng.r(5)!=0)enemy-=1+w.rng.r(v[1]);
  if(enemy>0)attack(w,c,0);
  if(enemy<=0||w.hp<=0||tick==2048){out[0]=enemy<=0;out[1]=tick;out[2]=mx(0,w.hp);out[3]=w.s.damage;out[4]=enemy>0&&w.hp>0;return;}
 }
}
__global__ void duel_kernel(Config c,const int*cases,int n,int reps,uint64_t seed,float*out){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i<n*reps)duel(c,cases+(i/reps)*5,seed+i,out+i*5);
}
extern "C" {
int power_cpu_duels(Config*c,const int*cases,int n,int reps,uint64_t seed,float*out){
 for(int i=0;i<n*reps;i++)duel(*c,cases+(i/reps)*5,seed+i,out+i*5);return 0;
}
int power_duels(Config*c,const int*cases,int n,int reps,uint64_t seed,float*out,void*stream){
 duel_kernel<<<(n*reps+127)/128,128,0,(cudaStream_t)stream>>>(*c,cases,n,reps,seed,out);return cudaGetLastError();
}
int power_duel_check(Config*cfg,Tables*tbl){
 Config c=*cfg;Tables t=*tbl;State initial={};initial.world_id=0;initial.reset_rng.seed(811,11);initial.parameter_rng.seed(811,13);reset(initial,c,t);
 bool found=false;for(int map=0;map<t.n_maps&&!found;map++){initial.map_id=map;found=single_scene(initial,c,t,0,100,0,1);}assert(found);
 int trials=0;
 for(int hp:{12,24})for(int pd:{3,5})for(int eh:{10,52})for(int ed:{4,12})for(int percent:{50,100})for(int seed=0;seed<16;seed++){
  State s=initial;s.player_max=hp;s.player_damage=pd;s.max_hp[0]=s.hp[0]=eh;s.damage_cap[0]=ed;s.w.hp=mx(1,(hp*percent+50)/100);s.w.regen=0;s.w.blocks=0;s.w.s={};s.w.rng.seed(mix(seed),17);
  int v[5]={hp,pd,eh,ed,percent};float expected[5],actual[OUT];duel(c,v,seed,expected);
  int d=-1;for(int j=0;j<8;j++)if(neighbor(s.player,j)==s.pos[0])d=j;assert(d>=0);
  for(int tick=1;tick<=2048;tick++){
   primitive_transition(s,c,t,d,2048,actual);
   if(actual[3]>0||actual[1]){assert(actual[3]==expected[0]);assert(actual[5]==expected[1]);assert(actual[4]==expected[2]);assert(actual[49]==expected[3]);assert(actual[7]==expected[4]);break;}
  }trials++;
 }
 return trials;
}
}
