import pathlib,subprocess
import run_ring_ablations as runner
ROOT=runner.ROOT.parents[1]
ASSETS=ROOT/'learning-runs/autoregressive-turn-cost-assets'
FLAGS=['-DPROGRESS_INPUT=2','-DKILL_MILLI=0','-DCLEAR_MILLI=1000','-DDEATH_MILLI=0','-DFRONTIER_TRAVEL=0','-DOGRE_COUNT=0','-DMONSTER_WAKE_LOS=1','-DTERRAIN_LOS=1','-DGLOBAL_ENEMIES=0','-DLEARN_ENEMIES=40','-DMULTI_MAP','-DSLEEP_ON','-DEXPLORE_REWARD','-DMARK_WALLS','-DEXPLORE_MILLI=0','-DFRONTIER_RING_MEMORY_WALLS_OBS','-DKNOWN_FRONTIER','-DFRONTIER_ROUTE_CUE_OBS','-DFAST_FRONTIER','-DLEARN_BLOCK_SIZE=4','-DCLEAR_PER_ENEMY_MILLI=0']
def build(clump,test=False):
 ASSETS.mkdir(parents=True,exist_ok=True);lib=ASSETS/(f'autoregressive-clump{clump}'+('-test' if test else '')+'.so')
 subprocess.run(['nvcc',('-O0' if test else '-O3'),'-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*FLAGS,f'-DCLUMP_MODE={clump}',str(runner.ROOT/'src'/('autoregressive_tests.cu' if test else 'learn.cu')),'-o',str(lib)],check=True)
 lib.with_suffix('.sha256').write_text(runner.digest(lib)+'\n');print(lib,flush=True)
if __name__=='__main__':
 for clump in [0,1]:build(clump)
