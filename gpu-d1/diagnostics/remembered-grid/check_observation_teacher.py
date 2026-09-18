"""CPU contract checks: local geometry, masking, episode reset, world isolation."""
import numpy as np
from observation_teacher import PreparedTeacher
from run import save_json
from runtime import ROOT

def main():
    local=np.zeros((2,5,15,15),np.float32);local[:,1]=1
    local[:,1,7,7:11]=0;local[:,2,7,7:11]=1;local[:,4,7,10]=1
    glob=np.zeros((2,6,16,16),np.float32);glob[:,0]=1;glob[:,5,8,8]=1
    mask=np.zeros((2,19),np.float32);mask[:,1]=1;mask[:,16]=1
    teacher=PreparedTeacher(True)
    assert np.array_equal(teacher.actions(local,glob,mask),[1,1])
    mask[0,18]=1;mask[1,1]=0
    assert np.array_equal(teacher.actions(local,glob,mask),[18,16])
    # A repeated observation has exactly reproducible decisions after reset.
    teacher.reset();local[:,4]=0;mask[:]=0;mask[:,[1,3,16]]=1
    local[:,1,7,3:8]=0;local[:,2,7,3:8]=1
    first=np.stack([teacher.actions(local,glob,mask) for _ in range(8)])
    teacher.reset();second=np.stack([teacher.actions(local,glob,mask) for _ in range(8)])
    assert np.array_equal(first,second)
    solo=PreparedTeacher(True)
    assert np.array_equal(first[:,1],np.array([solo.actions(local[1:],glob[1:],mask[1:])[0] for _ in range(8)]))
    report=dict(local_stair_path=True,masked_action_fallback=True,exit_action=True,reset_reproducible=True,world_isolation=True,
                interface='Only local categorical crop, coarse global map and mask. No other inputs or simulator callbacks.')
    save_json(ROOT/'results/observation-teacher-check.json',report);print(report)
if __name__=='__main__':main()
