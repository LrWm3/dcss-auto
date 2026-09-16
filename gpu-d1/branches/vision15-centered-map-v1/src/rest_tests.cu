#include "learn.cu"
HD void isolated(State&s,Config c,Tables t,int hp){
 s={};s.map_id=0;s.player=35*W+40;s.w.hp=hp;s.killed=REQUIRED-1;
 for(int p=0;p<N;p++){s.occ[p]=-1;s.frontier_slot[p]=-1;}
 for(int j=0;j<ENEMIES;j++){s.enemy_slot[j]=-1;s.energy[j]=-30000;}
 reveal(s,t);update_knowledge(s,c,t);
}
HD void place(State&s,Config c,Tables t,int distance,bool awake){
 int p=35*W+40+distance;s.pos[3]=p;s.hp[3]=16;s.occ[p]=3;s.awake[3]=awake;s.energy[3]=awake?70:-30000;update_knowledge(s,c,t);
}
void rest_test_kernel(State*workspace,Config c,Tables t,int*result,float*obs,float*mask){
 float out[OUT],step[OUT];
 State &initial=workspace[0],&macro=workspace[1],&manual=workspace[2],&sleeper=workspace[3],&waking=workspace[4],&incoming=workspace[5],&deadline=workspace[6];
 isolated(initial,c,t,3);macro=initial;manual=initial;
 transition(macro,c,t,9,2048,out);int count=0;float reward=0;
 do{primitive_transition(manual,c,t,8,2048,step);reward+=step[0];count++;}while(manual.w.hp<c.hp);
 manual.decisions=1;
 const unsigned char*a=(const unsigned char*)&macro,*b=(const unsigned char*)&manual;
 for(int j=0;j<sizeof(State);j++)assert(a[j]==b[j]);
 assert(out[35]==count && out[36] && out[0]==reward && !out[37]);
 observe(macro,c,t,obs,mask);assert(!mask[9] && obs[PLAYER_OBS+1]==count/2048.f);
 isolated(sleeper,c,t,3);place(sleeper,c,t,7,false);
 observe(sleeper,c,t,obs,mask);assert(mask[9] && obs[SLEEP_OBS+sleeper.enemy_slot[3]]==1);
 transition(sleeper,c,t,9,2048,out);assert(out[36] && !sleeper.awake[3] && sleeper.w.hp==18);
 isolated(waking,c,t,3);place(waking,c,t,6,false);
 observe(waking,c,t,obs,mask);assert(mask[9]);
 transition(waking,c,t,9,2048,out);assert(out[35]==1 && out[37] && waking.awake[3]);
 observe(waking,c,t,obs,mask);assert(!mask[9] && obs[SLEEP_OBS+waking.enemy_slot[3]]==-1);
 isolated(incoming,c,t,3);place(incoming,c,t,8,true);
 observe(incoming,c,t,obs,mask);assert(mask[9] && obs[SLEEP_OBS+incoming.enemy_slot[3]]==-1 && obs[454]==1);
 transition(incoming,c,t,9,2048,out);assert(out[35]==1 && out[37]);
 isolated(deadline,c,t,1);deadline.ticks=2047;deadline.decisions=13;
 transition(deadline,c,t,9,2048,out);assert(out[1] && out[7] && out[5]==2048 && out[35]==1 && deadline.ticks==0);
 observe(initial,c,t,obs,mask);
 for(int j=654;j<733;j++)assert(obs[j]==0);
 for(int p=0;p<N;p++)assert(obs[MAP_OBS+p]==(floor_at(t,initial.map_id,p)?1.f:-1.f));
 assert(reveal(initial,t)==0);
 *result=count;
}
extern "C" int rest_self_test(State*s,Config*c,Tables*t,int*result,float*obs,float*mask,void*stream){rest_test_kernel(s,*c,*t,result,obs,mask);return cudaGetLastError();}
