#include "learn.cu"
// CPU semantic checks supplement paired CPU/CUDA rollout checks in preflight.py.
extern "C" int stairs_semantic_test(Config *cfg,Tables *tables) {
 Config c=*cfg;Tables t=*tables;State s={};s.w.rng.seed(123,1);reset(s,c,t);
 float obs[OBS],other[OBS],mask[ACTIONS],out[OUT];
 observe(s,c,t,obs,mask);
 assert(!known_stairs(s) && !mask[18]);
 for(int j=STAIR_OBS;j<OBS;j++)assert(obs[j]==0);
 // Hidden stair placement must not affect any policy observation or action mask.
 State copy=s;
 for(int k=0;k<3;k++)copy.stairs[k]=s.stairs[(k+1)%3];
 observe(copy,c,t,other,mask);assert(!memcmp(obs,other,sizeof(obs)));
 int alternate=-1;
 for(int j=0;j<cell_count(t,s.map_id);j++) {
  int p=cells_map(t,s.map_id)[j];
  if(!s.seen[p] && p!=s.stairs[0] && p!=s.stairs[1] && p!=s.stairs[2]){alternate=p;break;}
 }
 assert(alternate>=0);copy.stairs[0]=alternate;
 observe(copy,c,t,other,mask);assert(!memcmp(obs,other,sizeof(obs)));
 // Removing all enemies no longer ends the episode.
 auto harmless=[&](){for(int i=0;i<c.count;i++){s.occ[s.pos[i]]=-1;s.hp[i]=0;s.energy[i]=-30000;}s.killed=REQUIRED;};
 harmless();transition(s,c,t,16,2048,out);assert(!out[1] && out[3]==REQUIRED);
 transition(s,c,t,18,2048,out);assert(!out[1] && out[0]<0); // Invalid descent waits.
 for(int k=0;k<3;k++) {
  reset(s,c,t);harmless();s.player=s.stairs[k];reveal(s,t);observe(s,c,t,obs,mask);
  assert(mask[18] && obs[STAIR_OBS+15] && obs[STAIR_OBS]>0);
  transition(s,c,t,16,2048,out);assert(!out[1]); // Standing is not descending.
  transition(s,c,t,18,2048,out);assert(out[1] && out[2] && !out[6] && !out[7]);
  assert(out[44]==k+1 && out[26]==1 && out[0]>.9999f);
 }
 reset(s,c,t);harmless();s.ticks=2047;transition(s,c,t,16,2048,out);
 assert(out[7] && !out[2] && out[5]==2048);
 // Remembering a stair out of LOS retains its cue; unknown floor is excluded.
 reset(s,c,t);harmless();int start=s.player,goal=s.stairs[0];
 s.player=goal;reveal(s,t);s.player=start;observe(s,c,t,obs,mask);
 assert(!in_view(s,t,goal) && obs[STAIR_OBS]>0);
 uint16_t ds[N];known_distances(s,t,ds,false);
 assert(bool(obs[STAIR_OBS+1])==(nearest_stair(s,ds)>=0));
 // Once a connected route has actually been revealed, the cue reaches the stair.
 for(int j=0;j<cell_count(t,s.map_id);j++) {s.player=cells_map(t,s.map_id)[j];reveal(s,t);}
 s.player=start;observe(s,c,t,obs,mask);assert(obs[STAIR_OBS+1]);
 int dir=-1;for(int d=0;d<8;d++)if(obs[STAIR_OBS+7+d])dir=d;
 assert(dir>=0 && s.viewed[neighbor(start,dir)]);
 // Descent can leave enemies alive and succeeds before their next action.
 reset(s,c,t);s.player=s.stairs[0];reveal(s,t);transition(s,c,t,18,2048,out);
 assert(out[2] && out[3]==0 && out[9]+out[10]==REQUIRED);
 return 0;
}
