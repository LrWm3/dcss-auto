#ifdef PROBE_SLEEP
#include "../../branches/vision15-rest-sleep-v1/src/learn.cu"
#else
#include "../../branches/vision15-rest-full-v1/src/learn.cu"
#endif
__global__ void setup_probe(State*s,int n,Config c,Tables t,const int*p,int reps,float*obs,float*mask){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 State&v=s[i];v={};v.map_id=0;v.player=35*W+40;v.w.hp=p[i*5];v.killed=REQUIRED-1;
 v.w.rng.seed(mix(930000+i%reps),i%reps+1);
 for(int j=0;j<N;j++){v.occ[j]=-1;v.frontier_slot[j]=-1;}
 for(int j=0;j<ENEMIES;j++){v.enemy_slot[j]=-1;v.energy[j]=-30000;}
 int id=p[i*5+1],pos=(35+p[i*5+4])*W+40+p[i*5+3];
 v.pos[id]=pos;v.hp[id]=p[i*5+2];v.occ[pos]=id;
 reveal(v,t);update_knowledge(v,c,t);observe(v,c,t,obs+i*OBS,mask+i*ACTIONS);
}
__global__ void read_probe(State*s,int n,Config c,Tables t,const int*p,float*out,int64_t*actions){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n)return;
 State&v=s[i];int id=p[i*5+1],pos=v.pos[id];float*q=out+i*5;
 q[0]=v.w.hp;q[1]=v.awake[id];q[2]=v.hp[id]>0&&in_view(v,t,pos);q[3]=cheb(v.player,pos);q[4]=v.hp[id];
 int dx=(pos%W>v.player%W)-(pos%W<v.player%W),dy=(pos/W>v.player/W)-(pos/W<v.player/W);
 actions[i]=8;
 for(int a=0;a<8;a++)if(neighbor(v.player,a)==v.player+dy*W+dx)actions[i]=a;
}
extern "C" int probe_init(State*s,int n,Config*c,Tables*t,const int*p,int reps,float*obs,float*mask,void*stream){setup_probe<<<(n+3)/4,4,0,(cudaStream_t)stream>>>(s,n,*c,*t,p,reps,obs,mask);return cudaGetLastError();}
extern "C" int probe_read(State*s,int n,Config*c,Tables*t,const int*p,float*out,int64_t*actions,void*stream){read_probe<<<(n+3)/4,4,0,(cudaStream_t)stream>>>(s,n,*c,*t,p,out,actions);return cudaGetLastError();}
