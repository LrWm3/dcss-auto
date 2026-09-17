"""Fixed practice-world allocation; resumable ordinary and tactical simulator state."""
import ctypes as C
import json
import torch
from learn_env_ring_multi import Env


class TacticalEnv(Env):
    def __init__(self,*args,**kwargs):
        self.ready=False
        super().__init__(*args,**kwargs)
        self.specs=json.loads((kwargs['corpus']/'scenarios.json').read_text())
        rows=[]
        families=['hallway','diagonal_pocket','passing_enemy','separated_groups']
        for item in self.metadata:
            s=self.specs[item['seed']]
            rows.append([(35+y)*80+40+x for x,y in [s['player'],s['goal'],*s['enemies']]]+[families.index(s['family']),s['orientation']])
        self.scenario_meta=torch.tensor(rows,dtype=torch.int32,device=self.device)
        p=C.c_void_p;i=C.c_int
        self.lib.tactical_reset.argtypes=[p,i,p,p,p,p,p,p,p]
        self.lib.tactical_probe.argtypes=[p,i,p,p,p,i,p,p,p]
        self.probe_actions=torch.empty(self.batch,dtype=torch.int64,device=self.device)
        self.probe_stats=torch.empty(self.batch,8,device=self.device)
        self.ready=True;self.inject(None)
    def probe(self,mode=0):
        self.check(self.lib.tactical_probe(self.state.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),self.scenario_meta.data_ptr(),mode,self.probe_actions.data_ptr(),self.probe_stats.data_ptr(),self.stream))
        return self.probe_actions,self.probe_stats
    def inject(self,selected):
        self.check(self.lib.tactical_reset(self.state.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),self.scenario_meta.data_ptr(),selected.data_ptr() if selected is not None else None,self.obs.data_ptr(),self.mask.data_ptr(),self.stream))
    def reset(self,seed):
        super().reset(seed)
        if self.ready:self.inject(None)
        return self.obs
    def step(self,actions,active=None):
        _,out=super().step(actions,active)
        ended=out[:,1]>0
        if active is not None:ended &= active
        self.inject(ended)
        return self.obs,out


class MixedEnv:
    def __init__(self,base,tactical,practice_worlds):
        self.base,self.tactical=base,tactical
        self.is_tactical=torch.arange(base.batch,device=base.device)<practice_worlds
        self.counts=torch.zeros(8,device=base.device,dtype=torch.float64)
        self.refresh()
    def __getattr__(self,name):return getattr(self.base,name)
    def refresh(self):
        self.obs=torch.where(self.is_tactical[:,None],self.tactical.obs,self.base.obs)
        self.mask=torch.where(self.is_tactical[:,None],self.tactical.mask,self.base.mask)
    def step(self,actions,active=None):
        enabled=torch.ones_like(self.is_tactical) if active is None else active
        ordinary=enabled&~self.is_tactical;tactical=enabled&self.is_tactical
        self.base.step(actions,active=ordinary);self.tactical.step(actions,active=tactical)
        self.out=torch.where(self.is_tactical[:,None],self.tactical.out,self.base.out)
        ended=(self.out[:,1]>0)&enabled
        self.counts+=torch.stack((ordinary.sum(),tactical.sum(),(ended&ordinary).sum(),(ended&tactical).sum(),(self.out[:,2]*ordinary).sum(),(self.out[:,2]*tactical).sum(),(self.out[:,6]*ordinary).sum(),(self.out[:,6]*tactical).sum()))
        self.refresh();return self.obs,self.out
    def snapshot(self):
        return dict(is_tactical=self.is_tactical.cpu(),counts=self.counts.cpu(),raw_obs=self.base.obs.cpu(),raw_mask=self.base.mask.cpu(),tactical_state=self.tactical.state.cpu(),tactical_obs=self.tactical.obs.cpu(),tactical_mask=self.tactical.mask.cpu())
    def restore(self,data):
        assert torch.equal(self.is_tactical.cpu(),data['is_tactical'])
        self.counts=data['counts'].to(self.device)
        self.base.obs.copy_(data['raw_obs']);self.base.mask.copy_(data['raw_mask'])
        self.tactical.state.copy_(data['tactical_state']);self.tactical.obs.copy_(data['tactical_obs']);self.tactical.mask.copy_(data['tactical_mask']);self.refresh()
