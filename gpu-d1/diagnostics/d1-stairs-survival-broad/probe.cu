#include "../d1-stairs-deaths/probe.cu"
__global__ void metadata_kernel(const State *s,int n,int *out) {
 int i=blockIdx.x*blockDim.x+threadIdx.x;
 if(i<n) {
  out[3*i]=s[i].map_id;
  out[3*i+1]=s[i].placement_clumped;
  out[3*i+2]=s[i].w.episode;
 }
}
extern "C" int audit_metadata(const State*s,int n,int*out,void*stream) {
 metadata_kernel<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,out);
 return cudaGetLastError();
}
