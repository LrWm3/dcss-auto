// Evaluation-only adapter; production simulation and training remain unchanged.
#include "learn.cu"
__global__ void subset_kernel(State *states,int n,Config c,Tables t,float *obs,float *mask) {
    int i=blockIdx.x*blockDim.x+threadIdx.x; if(i>=n) return;
    State &s=states[i];
    assert(s.ticks==0 && s.killed==0 && c.count>=1 && c.count<=ENEMIES);
    for(int j=c.count;j<ENEMIES;j++) {
        if(s.hp[j]>0) { assert(s.occ[s.pos[j]]==j); s.occ[s.pos[j]]=-1; }
        s.hp[j]=0; s.energy[j]=-30000; s.awake[j]=0;
    }
    observe(s,c,t,obs+i*OBS,mask+i*9);
}
extern "C" int eval_subset(State *s,int n,Config *c,Tables *t,float *obs,float *mask,void *stream) {
    subset_kernel<<<(n+127)/128,128,0,(cudaStream_t)stream>>>(s,n,*c,*t,obs,mask);
    return cudaGetLastError();
}
