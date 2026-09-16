// Policy-only code: receives observations/masks and its own terrain memory.
// No simulator state, hidden enemies, true floor table or oracle distances.
#include <cuda_runtime.h>
#include <stdint.h>
constexpr int W=80,H=70,N=W*H;
__device__ int neighbor(int p,int d){const int dx[8]={0,1,0,-1,1,1,-1,-1},dy[8]={-1,0,1,0,-1,1,1,-1};int x=p%W+dx[d],y=p/W+dy[d];return x>=0&&x<W&&y>=0&&y<H?y*W+x:-1;}
__global__ void choose(const float *obs,const float *masks,int8_t *memory,int64_t *actions,int *reason,const bool *active,int n,int width,int side,int na,bool rest){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n||!active[i])return;
 const float *o=obs+i*width,*mask=masks+i*na;int8_t *known=memory+i*N;
 int cells=side*side,player_obs=2*cells+200;
 int x=__float2int_rn(o[player_obs+2]*80),y=__float2int_rn(o[player_obs+3]*70),player=y*W+x;
 int radius=side/2,frontier=player_obs+4+8*(radius+1);
 for(int j=0;j<cells;j++){int px=x+j%side-radius,py=y+j/side-radius;if(px>=0&&px<W&&py>=0&&py<H&&o[j]!=0)known[py*W+px]=o[j]>0?1:-1;}
 actions[i]=8;reason[i]=4; // idle: no reachable visible enemy or frontier route
 if(rest&&na>9&&mask[9]>0){actions[i]=9;reason[i]=3;return;}
 // Adjacent visible enemies: lowest HP; fixed compass tie break.
 int adjacent=-1;float besthp=1e9f;
 for(int d=0;d<8;d++)if(mask[d]>0){int p=neighbor(player,d);
  for(int k=0;k<40;k++){const float *e=o+2*cells+5*k;if(e[4]<=0)continue;
   int ex=x+__float2int_rn(e[0]*80),ey=y+__float2int_rn(e[1]*70);
   if(p==ey*W+ex&&e[2]<besthp){besthp=e[2];adjacent=d;}
  }
 }
 if(adjacent>=0){actions[i]=adjacent;reason[i]=0;return;}
 bool visible=false;for(int k=0;k<40;k++)visible|=o[2*cells+5*k+4]>0;
 if(visible){
  uint16_t ds[N];int16_t queue[N];for(int p=0;p<N;p++)ds[p]=65535;
  ds[player]=0;queue[0]=player;int head=0,tail=1;
  while(head<tail){int p=queue[head++];for(int d=0;d<8;d++){int q=neighbor(p,d);if(q>=0&&known[q]==1&&ds[q]==65535){ds[q]=ds[p]+1;queue[tail++]=q;}}}
  int target=-1,bd=65535;
  for(int k=0;k<40;k++){const float *e=o+2*cells+5*k;if(e[4]<=0)continue;
   int ex=x+__float2int_rn(e[0]*80),ey=y+__float2int_rn(e[1]*70);
   if(ex>=0&&ex<W&&ey>=0&&ey<H){int p=ey*W+ex;if(ds[p]<bd){target=p;bd=ds[p];}}
  }
  if(target>=0&&bd>0){int p=target;while(ds[p]>1){int prev=-1;for(int d=0;d<8;d++){int q=neighbor(p,d);if(q>=0&&int(ds[q])+1==ds[p]){prev=q;break;}}if(prev<0)break;p=prev;}
   for(int d=0;d<8;d++)if(neighbor(player,d)==p&&mask[d]>0){actions[i]=d;reason[i]=1;return;}
  }
 }
 // Same nearest-known-frontier route cue exposed to the learned policies.
 if(o[frontier]>0){
  for(int d=0;d<8;d++)if(o[frontier+7+d]>0&&mask[d]>0){actions[i]=d;reason[i]=2;return;}
  // If already at the anchor, probe its first unknown neighbor, as supplied
  // by the observation. No hidden floor lookup is made.
  if(o[frontier+1]==0&&o[frontier+2]==0){int dx=__float2int_rn(o[frontier+5]),dy=__float2int_rn(o[frontier+6]);int target=(y+dy)*W+x+dx;
   for(int d=0;d<8;d++)if(neighbor(player,d)==target&&mask[d]>0){actions[i]=d;reason[i]=2;return;}
  }
 }
}
extern "C" int local_seek(const float *o,const float *m,int8_t *memory,int64_t *actions,int *reason,const bool *active,int n,int width,int side,int na,int rest,void *stream){
 choose<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(o,m,memory,actions,reason,active,n,width,side,na,rest);return cudaGetLastError();
}
