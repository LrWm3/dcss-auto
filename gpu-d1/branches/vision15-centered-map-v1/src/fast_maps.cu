#include <cuda_runtime.h>
#include <cuda_fp16.h>
#include <math.h>
template<class T> __global__ void encode(const float*obs,const float*enemy,T*out,int n,int stride){
 int i=blockIdx.x*blockDim.x+threadIdx.x;if(i>=n*8*160*160*3)return;
 int c=i%3,pixel=i/3,x=pixel%160,y=(pixel/160)%160;
 int sample=pixel/(160*160),b=sample%n,g=sample/n,dx=x-79,dy=y-79,r=g%4;
 int sx=r==0?dx:r==1?dy:r==2?-dx:-dy;
 int sy=r==0?dy:r==1?-dx:r==2?-dy:dx;if(g>=4)sx=-sx;
 int px=lrintf(obs[b*stride+652]*80),py=lrintf(obs[b*stride+653]*70);
 int wx=px+sx,wy=py+sy;float value=0;
 if(x<159 && y<159 && wx>=0 && wx<80 && wy>=0 && wy<70){
  int p=wy*80+wx;
  value=c==0?obs[b*stride+999+p]:enemy[b*11200+(c-1)*5600+p];
 }
 out[i]=T(value);
}
extern "C" int encode_maps(const float*obs,const float*enemy,void*out,int n,int stride,int half,void*stream){
 int blocks=(n*8*160*160*3+255)/256;
 if(half)encode<<<blocks,256,0,(cudaStream_t)stream>>>(obs,enemy,(__half*)out,n,stride);
 else encode<<<blocks,256,0,(cudaStream_t)stream>>>(obs,enemy,(float*)out,n,stride);
 return cudaGetLastError();
}
