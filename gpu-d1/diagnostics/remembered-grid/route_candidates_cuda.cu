#include <cuda_runtime.h>
#include <cstdint>
constexpr int S=5600,W=80,H=70;
__device__ int adjacent(int p,int a){const int dx[]={0,1,0,-1,1,1,-1,-1},dy[]={-1,0,1,0,-1,1,1,-1};int x=p%W+dx[a],y=p/W+dy[a];return x<0||x>=W||y<0||y>=H?-1:y*W+x;}
__global__ void route_kernel(int n,const uint8_t*grids,int stride,const float*masks,int8_t*first,uint8_t*candidates,int64_t*goals,int64_t*actions){
 int b=blockIdx.x;if(b>=n)return;auto g=grids+b*stride;auto m=masks+b*19;auto f=first+b*S;auto c=candidates+b*S;
 __shared__ int16_t d[S],queue[S];__shared__ uint8_t front[S],seen[S];__shared__ int player;
 for(int v=threadIdx.x;v<S;v+=blockDim.x){d[v]=-1;front[v]=seen[v]=c[v]=0;f[v]=-1;if(g[5*S+v])player=v;}
 __syncthreads();
 if(threadIdx.x==0){int head=0,tail=1;queue[0]=player;d[player]=0;
  while(head<tail){int v=queue[head++];for(int a=0;a<8;a++){int u=adjacent(v,a);if(u<0||!g[u]||d[u]>=0||(v==player&&!m[a]))continue;d[u]=d[v]+1;f[u]=v==player?a:f[v];queue[tail++]=u;}}
 }
 __syncthreads();
 for(int v=threadIdx.x;v<S;v+=blockDim.x)if(d[v]>=0){if(g[4*S+v]&&v!=player)c[v]=1;
  for(int a=0;a<8;a++){int u=adjacent(v,a);if(u>=0&&!g[u]&&!g[S+u])front[v]=1;}
 }
 __syncthreads();
 if(threadIdx.x==0){
  for(int start=0;start<S;start++)if(front[start]&&!seen[start]){
   int head=0,tail=1,rep=S;queue[0]=start;seen[start]=1;
   while(head<tail){int v=queue[head++];if(v!=player&&v<rep)rep=v;
    for(int a=0;a<8;a++){int u=adjacent(v,a);if(u>=0&&front[u]&&!seen[u]){seen[u]=1;queue[tail++]=u;}}
   }if(rep<S)c[rep]=1;
  }
  int best=-1;for(int v=0;v<S;v++)if(c[v]&&g[4*S+v]&&(best<0||d[v]<d[best]))best=v;
  if(best<0)for(int v=0;v<S;v++)if(c[v]&&(best<0||d[v]<d[best]))best=v;
  goals[b]=best;actions[b]=m[18]>0?18:(best>=0?f[best]:16);
 }
}
extern "C" int gpu_routes(int n,const uint8_t*g,int stride,const float*m,int8_t*f,uint8_t*c,int64_t*goals,int64_t*actions,void*stream){route_kernel<<<n,256,0,(cudaStream_t)stream>>>(n,g,stride,m,f,c,goals,actions);return cudaGetLastError();}
