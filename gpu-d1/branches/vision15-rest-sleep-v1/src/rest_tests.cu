#include "learn.cu"
HD State isolated(Config c,Tables t,int hp){
 State s={};s.map_id=0;s.player=35*W+40;s.w.hp=hp;s.killed=REQUIRED-1;
 for(int p=0;p<N;p++){s.occ[p]=-1;s.frontier_slot[p]=-1;}
 for(int j=0;j<ENEMIES;j++){s.enemy_slot[j]=-1;s.energy[j]=-30000;}
 reveal(s,t);update_knowledge(s,c,t);return s;
}
__global__ void rest_test_kernel(Config c,Tables t,int*result){
 float out[OUT],obs[OBS],mask[ACTIONS],step[OUT];
 State initial=isolated(c,t,3),macro=initial,manual=initial;
 observe(initial,c,t,obs,mask);assert(mask[9]==1);
 transition(macro,c,t,9,2048,out);
 int count=0;float reward=0;
 do{primitive_transition(manual,c,t,8,2147483647,step);reward+=step[0];count++;}while(manual.w.hp<c.hp);
 manual.decisions=1;
 const unsigned char*a=(const unsigned char*)&macro,*b=(const unsigned char*)&manual;
 for(int j=0;j<sizeof(State);j++)assert(a[j]==b[j]);
 assert(out[26]==count && out[35]==count && out[34]==1 && out[36]==1 && !out[37]);
 assert(out[0]==reward && out[39]==15 && macro.decisions==1);
 observe(macro,c,t,obs,mask);assert(mask[9]==0 && obs[PLAYER_OBS+1]==1/2048.f);
 State visible=isolated(c,t,3);int p=35*W+47;visible.pos[3]=p;visible.hp[3]=16;visible.occ[p]=3;visible.awake[3]=0;
 update_knowledge(visible,c,t);observe(visible,c,t,obs,mask);assert(visible_enemy(visible,c,t) && mask[9]==0);
 assert(obs[SLEEP_OBS+visible.enemy_slot[3]]==1);
 visible.awake[3]=1;observe(visible,c,t,obs,mask);assert(obs[SLEEP_OBS+visible.enemy_slot[3]]==-1);
 visible.awake[3]=0;observe(visible,c,t,obs,mask);
 transition(visible,c,t,9,2048,out);assert(out[38]==1 && out[26]==1 && out[34]==0 && !visible.awake[3]);
 State approaching=isolated(c,t,3);p=35*W+48;approaching.pos[3]=p;approaching.hp[3]=16;approaching.occ[p]=3;approaching.awake[3]=1;approaching.energy[3]=70;
 observe(approaching,c,t,obs,mask);assert(mask[9]==1);
 for(int j=0;j<ENEMIES;j++)assert(obs[SLEEP_OBS+j]==0);
 transition(approaching,c,t,9,2048,out);assert(out[35]==1 && out[37]==1 && !out[36] && visible_enemy(approaching,c,t));
 observe(approaching,c,t,obs,mask);assert(mask[9]==0);
 assert(obs[SLEEP_OBS+approaching.enemy_slot[3]]==-1);
 int remembered_slot=approaching.enemy_slot[3];approaching.occ[approaching.pos[3]]=-1;approaching.pos[3]=35*W+48;approaching.occ[approaching.pos[3]]=3;
 update_knowledge(approaching,c,t);observe(approaching,c,t,obs,mask);assert(obs[SLEEP_OBS+remembered_slot]==0);
 State deadline=isolated(c,t,1);deadline.ticks=4096;deadline.decisions=2047;
 transition(deadline,c,t,9,2048,out);assert(out[1] && out[7] && out[5]>4096 && out[35]>1 && deadline.decisions==0 && deadline.ticks==0);
 *result=count;
}
extern "C" int rest_self_test(Config*c,Tables*t,int*result,void*stream){rest_test_kernel<<<1,1,0,(cudaStream_t)stream>>>(*c,*t,result);return cudaGetLastError();}
