#include "../../branches/d1-stairs-v2/src/learn.cu"
// Diagnostics only: change future randomness while preserving the entire scene.
__global__ void reseed_kernel(State *s,int n,uint64_t seed) {
 int i=blockIdx.x*blockDim.x+threadIdx.x;
 if(i<n)s[i].w.rng.seed(mix(seed+i),i+17);
}
extern "C" int audit_reseed(State*s,int n,uint64_t seed,void*stream) {
 reseed_kernel<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,seed);
 return cudaGetLastError();
}
