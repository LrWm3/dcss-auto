import hashlib,pathlib,subprocess
HERE=pathlib.Path(__file__).resolve().parents[1]
ROOT=HERE.parents[1]
ASSETS=ROOT/"learning-runs/d1-stairs-assets"
FLAGS=['-DPROGRESS_INPUT=2','-DKILL_MILLI=0','-DCLEAR_MILLI=1000','-DDEATH_MILLI=0','-DFRONTIER_TRAVEL=0','-DOGRE_COUNT=0','-DMONSTER_WAKE_LOS=1','-DTERRAIN_LOS=1','-DGLOBAL_ENEMIES=0','-DLEARN_ENEMIES=40','-DMULTI_MAP','-DSLEEP_ON','-DEXPLORE_REWARD','-DMARK_WALLS','-DEXPLORE_MILLI=0','-DFRONTIER_RING_MEMORY_WALLS_OBS','-DKNOWN_FRONTIER','-DFRONTIER_ROUTE_CUE_OBS','-DFAST_FRONTIER','-DLEARN_BLOCK_SIZE=4','-DCLEAR_PER_ENEMY_MILLI=0']
def build(clump, test=False):
 ASSETS.mkdir(parents=True,exist_ok=True)
 lib=ASSETS/(f'stairs-clump{clump}'+('-test' if test else '')+'.so')
 subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*FLAGS,f'-DCLUMP_MODE={clump}',str(HERE/'src'/('tests.cu' if test else 'learn.cu')),'-o',str(lib)],check=True)
 lib.with_suffix('.sha256').write_text(hashlib.sha256(lib.read_bytes()).hexdigest()+'\n')
 print(lib,flush=True)
 return lib
if __name__=='__main__':
 for c in [0,1]:build(c)
