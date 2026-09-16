// Retreat overlay: observed terrain + visible enemy/sleep records only.
#include <cuda_runtime.h>
#include <stdint.h>
constexpr int W=80,H=70,N=W*H;
__device__ int nb(int p,int d){const int dx[8]={0,1,0,-1,1,1,-1,-1},dy[8]={-1,0,1,0,-1,1,1,-1};int x=p%W+dx[d],y=p/W+dy[d];return x>=0&&x<W&&y>=0&&y<H?y*W+x:-1;}
__device__ bool hall(int p,const int8_t *known){
 if(known[p]!=1)return false;
 const int a[4]={0,1,4,5},b[4]={2,3,6,7};
 for(int axis=0;axis<4;axis++){bool ok=true;for(int d=0;d<8;d++){int q=nb(p,d);int wanted=(d==a[axis]||d==b[axis])?1:-1;if(q<0||known[q]!=wanted){ok=false;break;}}if(ok)return true;}
 return false;
}
__device__ void bfs(int player,const int8_t *known,uint16_t *ds){
 int16_t queue[N];for(int p=0;p<N;p++)ds[p]=65535;ds[player]=0;queue[0]=player;int h=0,t=1;
 while(h<t){int p=queue[h++];for(int d=0;d<8;d++){int q=nb(p,d);if(q>=0&&known[q]==1&&ds[q]==65535){ds[q]=ds[p]+1;queue[t++]=q;}}}
}
__device__ int first(int player,int target,const uint16_t *ds){
 if(target<0||target==player||ds[target]==65535)return -1;
 int p=target;while(ds[p]>1){int prev=-1;for(int d=0;d<8;d++){int q=nb(p,d);if(q>=0&&int(ds[q])+1==ds[p]){prev=q;break;}}if(prev<0)return -1;p=prev;}
 for(int d=0;d<8;d++)if(nb(player,d)==p)return d;return -1;
}
// State: 0 eligible, 1 walking to fixed target, 2 holding hallway,
// 3 spent/aborted: normal combat until no enemies remain visible.
// Events: start, arrive, blocked_enemy, wait, move, adjacent_resume,
//         visibility_reset, no_hall, route_abort, lockout_decision, inferred_block (filled after the step).
__global__ void overlay(const float *obs,const float *masks,const int8_t *memory,int64_t *actions,int *state,int *events,const bool *active,int n,int width,int side,int na){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n||!active[i])return;
 int *s=state+2*i,*e=events+11*i;for(int k=0;k<11;k++)e[k]=0;
 const float *o=obs+i*width,*mask=masks+i*na;const int8_t *known=memory+i*N;
 int cells=side*side,po=2*cells+200,sleep=po+4+8*(side/2+1)+15+cells+1;
 int x=__float2int_rn(o[po+2]*80),y=__float2int_rn(o[po+3]*70),player=y*W+x;
 int positions[40],count=0,awake=0,sx=0,sy=0;bool adjacent=false;
 for(int k=0;k<40;k++){const float *r=o+2*cells+5*k;if(r[4]<=0)continue;
  int dx=__float2int_rn(r[0]*80),dy=__float2int_rn(r[1]*70);positions[count++]=(y+dy)*W+x+dx;
  adjacent|=(abs(dx)<=1&&abs(dy)<=1&&(dx||dy));
  if(o[sleep+k]<0){awake++;sx+=dx;sy+=dy;}
 }
 if(count==0){if(s[0])e[6]=1;s[0]=0;s[1]=-1;return;}
 if(s[0]==3){e[9]=1;return;}
 uint16_t ds[N];bool have_ds=false;
 if(s[0]==0){
  if(awake<2)return;
  int target=-1;
  if(hall(player,known))target=player;
  else {
   bfs(player,known,ds);have_ds=true;int bd=65535;
   for(int p=0;p<N;p++)if(ds[p]>0&&ds[p]<bd&&hall(p,known)){
    int dx=p%W-x,dy=p/W-y;if(dx*sx+dy*sy>=0)continue;
    int d=first(player,p,ds);if(d<0)continue;int q=nb(player,d);
    if((q%W-x)*sx+(q/W-y)*sy>=0)continue;
    bd=ds[p];target=p;
   }
  }
  if(target<0){e[7]=1;return;}
  s[0]=1;s[1]=target;e[0]=1;
 }
 if(s[0]==1){
  if(player==s[1]){s[0]=2;e[1]=1;}
  else {
   if(!have_ds)bfs(player,known,ds);
   int d=first(player,s[1],ds);
   if(d<0||mask[d]<=0){s[0]=3;e[8]=1;return;}
   int q=nb(player,d);
   for(int k=0;k<count;k++)if(positions[k]==q){s[0]=3;e[2]=1;return;}
   actions[i]=d;e[4]=1;return;
  }
 }
 if(s[0]==2){
  if(adjacent){s[0]=3;e[5]=1;return;}
  actions[i]=8;e[3]=1;return;
 }
}
extern "C" int hallway_retreat(const float *obs,const float *mask,const int8_t *memory,int64_t *actions,int *state,int *events,const bool *active,int n,int width,int side,int na,void *stream){
 overlay<<<(n+31)/32,32,0,(cudaStream_t)stream>>>(obs,mask,memory,actions,state,events,active,n,width,side,na);return cudaGetLastError();
}
