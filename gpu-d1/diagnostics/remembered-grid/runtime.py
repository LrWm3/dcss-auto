import ctypes as C
import hashlib,importlib.util,json,subprocess,time
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from maps import ROOT,G,generate
HERE=Path(__file__).resolve().parent
OUT=ROOT/'learning-runs/remembered-grid'
spec=importlib.util.spec_from_file_location('grid_stats',HERE.parent/'d1-stat-generalization/runtime.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    files=[HERE/'native.cu',HERE.parent/'d1-stat-generalization/learn.cu',ROOT/'branches/d1-stairs-v2/src/sim.h']
    key={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    flag=OUT/'build.json'
    if not flag.exists() or json.loads(flag.read_text())!=key:
        subprocess.run(['nvcc','-O3','-std=c++17','-arch=sm_75','-ccbin','/usr/bin/g++-12','-shared','-Xcompiler','-fPIC',*old.FLAGS,'-DCLUMP_MODE=0',str(HERE/'native.cu'),'-o',str(OUT/'grid.so')],check=True)
        flag.write_text(json.dumps(key,indent=2))
    generate(OUT/'maps')

_CACHE={}
_CONFIG=None
class Env:
    def __init__(self,split='train',batch=128,map_dir=None,grid_shape=(G,G),library=None):
        self.split=split;self.batch=batch
        map_dir=Path(map_dir) if map_dir is not None else OUT/'maps'
        key=(str(map_dir),split)
        if key not in _CACHE:
            z=np.load(map_dir/f'{split}.npz')
            arr={k:torch.from_numpy(z[k].view(np.int16) if z[k].dtype==np.uint16 else z[k]).cuda() for k in z.files}
            _CACHE[key]=arr
        self.arrays=_CACHE[key];a=self.arrays
        self.scenes=a['scenarios'];self.profiles=torch.tensor([[18,4,1]+[24]*6+[20]*6],device='cuda',dtype=torch.int32)
        self.assign=torch.zeros(batch,device='cuda',dtype=torch.int32)
        self.tables=old.Tables(self.profiles.data_ptr(),self.assign.data_ptr(),1,0,batch,*[a[k].data_ptr() for k in ['floor','cells','index','distance']],int(a['ncells'][0]),a['ncells'].data_ptr(),a['offsets'].data_ptr(),len(a['floor']),-1,a['los'].data_ptr())
        global _CONFIG
        if _CONFIG is None:
            from learn_env import load_map
            header,kinds,_=load_map();ac=header[2]//100;gdr=[int((65536*(ac+j))**.25) for j in range(2)];_CONFIG=[1,*header[:7],1,*gdr,*kinds]
        values=_CONFIG
        self.config=(C.c_int*len(values))(*values);self.lib=C.CDLL(str(library if library is not None else OUT/'grid.so'));p=C.c_void_p;i=C.c_int
        self.lib.grid_init.argtypes=[p,p,i,p,p,p,p,C.c_uint64,p]
        self.lib.grid_export.argtypes=[p,p,i,p,p,p,p,p,p,i,p]
        self.lib.grid_step.argtypes=[p,p,i,p,p,p,p,i,p,p]
        self.state=torch.empty(batch,self.lib.learn_state_bytes(),device='cuda',dtype=torch.uint8)
        self.memory=torch.empty(batch,self.lib.grid_memory_bytes(),device='cuda',dtype=torch.uint8)
        self.grid=torch.empty(batch,11,*grid_shape,device='cuda',dtype=torch.uint8)
        self.mask=torch.empty(batch,19,device='cuda');self.stats=torch.empty(batch,4,device='cuda')
        self.labels=torch.empty(batch,device='cuda',dtype=torch.long);self.meta=torch.empty(batch,6,device='cuda',dtype=torch.int32)
        self.out=torch.zeros(batch,53,device='cuda');self.active=torch.ones(batch,device='cuda',dtype=torch.bool)
    @property
    def stream(self):return torch.cuda.current_stream().cuda_stream
    def check(self,z):
        if z:raise RuntimeError(f'CUDA call: {z}')
    def reset(self,ids=None,seed=0,kinds=(0,1,2),labels=True):
        if ids is None:
            chosen=torch.randint(len(kinds),(self.batch,),device='cuda');ids=torch.empty(self.batch,device='cuda',dtype=torch.long)
            for j,k in enumerate(kinds):
                eligible=torch.where(self.scenes[:,1]==k)[0];draw=eligible[torch.randint(len(eligible),(self.batch,),device='cuda')];ids=torch.where(chosen==j,draw,ids)
        self.ids=ids.int().contiguous();self.active.fill_(True);self.out.zero_()
        self.check(self.lib.grid_init(self.state.data_ptr(),self.memory.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),self.scenes.data_ptr(),self.ids.data_ptr(),seed,self.stream));self.observe(labels)
    def observe(self,labels=True):
        self.check(self.lib.grid_export(self.state.data_ptr(),self.memory.data_ptr(),self.batch,C.byref(self.tables),self.grid.data_ptr(),self.mask.data_ptr(),self.stats.data_ptr(),self.labels.data_ptr(),self.meta.data_ptr(),int(labels),self.stream))
    def step(self,actions,limit=512,labels=True):
        self.check(self.lib.grid_step(self.state.data_ptr(),self.memory.data_ptr(),self.batch,C.byref(self.config),C.byref(self.tables),actions.long().contiguous().data_ptr(),self.active.data_ptr(),limit,self.out.data_ptr(),self.stream))
        self.active &= ~self.out[:,1].bool();self.observe(labels)

class Policy(nn.Module):
    def __init__(self,arm='memory'):
        super().__init__();self.arm=arm
        self.local=nn.Sequential(nn.Conv2d(11,16,3,padding=1),nn.ReLU(),nn.Conv2d(16,16,3,padding=1),nn.ReLU(),nn.Flatten(),nn.Linear(16*15*15,64),nn.ReLU())
        self.global_net=nn.Sequential(nn.Conv2d(13,16,3,padding=1),nn.ReLU(),nn.Conv2d(16,24,3,stride=2,padding=1),nn.ReLU(),nn.Conv2d(24,32,3,stride=2,padding=1),nn.ReLU(),nn.Conv2d(32,32,3,padding=2,dilation=2),nn.ReLU(),nn.Flatten(),nn.Linear(32*8*8,128),nn.ReLU())
        self.head=nn.Sequential(nn.Linear(194,128),nn.ReLU(),nn.Linear(128,19))
        yy,xx=torch.meshgrid(torch.arange(G),torch.arange(G),indexing='ij');self.register_buffer('xy',torch.stack([xx,yy]).float()[None],persistent=False)
        yy,xx=torch.meshgrid(torch.arange(-7,8),torch.arange(-7,8),indexing='ij');self.register_buffer('crop_xy',torch.stack([xx,yy],-1).float()[None],persistent=False)
    def forward(self,grid,mask,stats,intervene=None):
        g=grid.float()/255.;pos=stats[:,2:4];coords=self.crop_xy+pos[:,None,None,:]
        local=F.grid_sample(g,coords/(G-1)*2-1,mode='nearest',align_corners=True)
        if self.arm=='terrain' or intervene=='erase_memory':
            visible=g[:,3:4];g=torch.cat([g[:,:6],g[:,6:]*visible],1)
            local=F.grid_sample(g,coords/(G-1)*2-1,mode='nearest',align_corners=True)
        lo=self.local(local)
        if self.arm=='local' or intervene=='erase_global':gl=torch.zeros(len(g),128,device=g.device)
        else:gl=self.global_net(torch.cat([g,(self.xy-pos[:,:,None,None])/G],1))
        logits=self.head(torch.cat([lo,gl,stats[:,:2]],1));return logits.masked_fill(mask==0,-1e9)

class SpatialPolicy(Policy):
    """Learned U-net preserves fine geometry while mixing distant map features.

    No search, goal selection, distances, or fixed propagation rule in forward.
    """
    def __init__(self,arm='memory'):
        super().__init__(arm)
        del self.global_net
        def block(a,b):return nn.Sequential(nn.Conv2d(a,b,3,padding=1),nn.ReLU(),nn.Conv2d(b,b,3,padding=1),nn.ReLU())
        self.fine=block(13,16);self.middle=block(16,24);self.coarse=block(24,32)
        self.context=nn.Sequential(nn.Conv2d(32,32,3,padding=2,dilation=2),nn.ReLU(),nn.Conv2d(32,32,3,padding=2,dilation=2),nn.ReLU())
        self.up_middle=block(56,24);self.up_fine=block(40,16)
        self.readout=nn.Sequential(nn.Linear(16*9,128),nn.ReLU())
        yy,xx=torch.meshgrid(torch.arange(-1,2),torch.arange(-1,2),indexing='ij');self.register_buffer('read_xy',torch.stack([xx,yy],-1).float()[None],persistent=False)
    def forward(self,grid,mask,stats,intervene=None):
        g=grid.float()/255.;pos=stats[:,2:4]
        if self.arm=='terrain' or intervene=='erase_memory':g=torch.cat([g[:,:6],g[:,6:]*g[:,3:4]],1)
        local=F.grid_sample(g,(self.crop_xy+pos[:,None,None,:])/(G-1)*2-1,mode='nearest',align_corners=True);lo=self.local(local)
        if self.arm=='local' or intervene=='erase_global':gl=torch.zeros(len(g),128,device=g.device)
        else:
            fine=self.fine(torch.cat([g,(self.xy-pos[:,:,None,None])/G],1))
            middle=self.middle(F.max_pool2d(fine,2));coarse=self.coarse(F.max_pool2d(middle,2));context=self.context(coarse)
            middle=self.up_middle(torch.cat([middle,F.interpolate(context,scale_factor=2,mode='nearest')],1))
            fine=self.up_fine(torch.cat([fine,F.interpolate(middle,scale_factor=2,mode='nearest')],1))
            read=F.grid_sample(fine,(self.read_xy+pos[:,None,None,:])/(G-1)*2-1,mode='nearest',align_corners=True).flatten(1)
            gl=self.readout(read)
        return self.head(torch.cat([lo,gl,stats[:,:2]],1)).masked_fill(mask==0,-1e9)

class PackedPolicy(SpatialPolicy):
    """Lossless 4x4 input packing, learned coarse U-net, full-resolution local view.

    Packing keeps every tile in a distinct channel; subsequent learned feature
    compression is not lossless. No routing or distance computation is used.
    Supports arbitrary rectangular maps with unknown-valued right/bottom padding.
    """
    def __init__(self,arm='memory',amp=True,factor=4):
        super().__init__(arm)
        self.amp=amp;self.factor=factor
        self.pack_project=nn.Sequential(nn.Conv2d(13*factor*factor,16,1),nn.ReLU())
        self.fine=nn.Sequential(nn.Conv2d(16,16,3,padding=1),nn.ReLU(),nn.Conv2d(16,16,3,padding=1),nn.ReLU())
        self.readout=nn.Sequential(nn.Linear(16*9+2,128),nn.ReLU())

    def forward(self,grid,mask,stats,intervene=None):
        with torch.autocast(device_type=grid.device.type,dtype=torch.float16,enabled=self.amp and grid.is_cuda):
            return self._forward(grid,mask,stats,intervene)

    def _forward(self,grid,mask,stats,intervene):
        h,w=grid.shape[-2:];pos=stats[:,2:4];g=grid.float().contiguous(memory_format=torch.channels_last)/255.
        scale=stats.new_tensor([w-1,h-1]);size=stats.new_tensor([w,h])
        if self.arm=='terrain' or intervene=='erase_memory':g=torch.cat([g[:,:6],g[:,6:]*g[:,3:4]],1)
        local=F.grid_sample(g,(self.crop_xy+pos[:,None,None,:])/scale*2-1,mode='nearest',align_corners=True);lo=self.local(local)
        if self.arm=='local' or intervene=='erase_global':gl=torch.zeros(len(g),128,device=g.device)
        else:
            yy,xx=torch.meshgrid(torch.arange(h,device=g.device),torch.arange(w,device=g.device),indexing='ij')
            xy=torch.stack([xx,yy]).float()[None]
            whole=torch.cat([g,(xy-pos[:,:,None,None])/size[None,:,None,None]],1)
            whole=F.pad(whole,(0,(-w)%(self.factor*4),0,(-h)%(self.factor*4)))
            fine=self.fine(self.pack_project(F.pixel_unshuffle(whole,self.factor)))
            middle=self.middle(F.max_pool2d(fine,2));coarse=self.coarse(F.max_pool2d(middle,2));context=self.context(coarse)
            middle=self.up_middle(torch.cat([middle,F.interpolate(context,size=middle.shape[-2:],mode='nearest')],1))
            fine=self.up_fine(torch.cat([fine,F.interpolate(middle,size=fine.shape[-2:],mode='nearest')],1))
            blockpos=torch.floor(pos/self.factor);blockscale=stats.new_tensor([fine.shape[-1]-1,fine.shape[-2]-1])
            read=F.grid_sample(fine,(self.read_xy+blockpos[:,None,None,:])/blockscale*2-1,mode='nearest',align_corners=True).flatten(1)
            gl=self.readout(torch.cat([read,(pos%self.factor)/(self.factor-1)],1))
        return self.head(torch.cat([lo,gl,stats[:,:2]],1)).float().masked_fill(mask==0,-1e9)

class Packed2Policy(PackedPolicy):
    def __init__(self,arm='memory',amp=True):
        super().__init__(arm,amp,factor=2)

class CroppedSpatialPolicy(SpatialPolicy):
    """Same weights/computation as SpatialPolicy, cropping the last decoder.

    Only the 3x3 readout is needed. Two 3x3 decoder convolutions require a 7x7
    input patch. Intermediate masking reproduces full-map zero padding even
    when the player is on the boundary. AMP is optional; FP32 is equivalent.
    """
    def __init__(self,arm='terrain',amp=True):
        super().__init__(arm);self.amp=amp;self.fast_pool=False
        yy,xx=torch.meshgrid(torch.arange(-3,4),torch.arange(-3,4),indexing='ij')
        self.register_buffer('patch_xy',torch.stack([xx,yy],-1)[None],persistent=False)
        yy,xx=torch.meshgrid(torch.arange(-4,5),torch.arange(-4,5),indexing='ij')
        self.register_buffer('middle_patch_xy',torch.stack([xx,yy],-1)[None],persistent=False)

    def pool(self,x):
        if not self.fast_pool:return F.max_pool2d(x,2)
        # Same 2x2 max and first-index tie rule, exposing fusion to Inductor.
        h,w=x.shape[-2:];h=h//2*2;w=w//2*2
        a=x[:,:,0:h:2,0:w:2];b=x[:,:,0:h:2,1:w:2]
        c=x[:,:,1:h:2,0:w:2];d=x[:,:,1:h:2,1:w:2]
        ab=torch.where(a>=b,a,b);cd=torch.where(c>=d,c,d)
        return torch.where(ab>=cd,ab,cd)

    def forward(self,grid,mask,stats,intervene=None):
        with torch.autocast(device_type=grid.device.type,dtype=torch.float16,enabled=self.amp and grid.is_cuda):
            return self._forward(grid,mask,stats,intervene)

    def _forward(self,grid,mask,stats,intervene):
        h,w=grid.shape[-2:];pos=stats[:,2:4];g=grid.float()/255.
        if self.amp:g=g.contiguous(memory_format=torch.channels_last)
        size=stats.new_tensor([w,h]);scale=size-1
        if self.arm=='terrain' or intervene=='erase_memory':g=torch.cat([g[:,:6],g[:,6:]*g[:,3:4]],1)
        lo=self.local(F.grid_sample(g,(self.crop_xy+pos[:,None,None,:])/scale*2-1,mode='nearest',align_corners=True))
        if self.arm=='local' or intervene=='erase_global':gl=torch.zeros(len(g),128,device=g.device)
        else:
            yy,xx=torch.meshgrid(torch.arange(h,device=g.device),torch.arange(w,device=g.device),indexing='ij');xy=torch.stack([xx,yy]).float()[None]
            fine=self.fine(torch.cat([g,(xy-pos[:,:,None,None])/size[None,:,None,None]],1))
            middle=self.middle(self.pool(fine));coarse=self.coarse(self.pool(middle));context=self.context(coarse)
            # Decode only the middle-layer region needed by the final patch.
            mh,mw=middle.shape[-2:];ch,cw=context.shape[-2:]
            center=torch.stack([torch.div(pos[:,0].long()*mw,w,rounding_mode='floor'),torch.div(pos[:,1].long()*mh,h,rounding_mode='floor')],1)
            qp=self.middle_patch_xy+center[:,None,None,:];qx,qy=qp[...,0],qp[...,1]
            mv=((qx>=0)&(qx<mw)&(qy>=0)&(qy<mh))[:,None]
            qi=(qy.clamp(0,mh-1)*mw+qx.clamp(0,mw-1)).flatten(1)
            skip=torch.gather(middle.flatten(2),2,qi[:,None].expand(-1,middle.shape[1],-1)).reshape(-1,middle.shape[1],9,9)*mv
            ci=(torch.div(qy.clamp(0,mh-1)*ch,mh,rounding_mode='floor')*cw+torch.div(qx.clamp(0,mw-1)*cw,mw,rounding_mode='floor')).flatten(1)
            lower=torch.gather(context.flatten(2),2,ci[:,None].expand(-1,context.shape[1],-1)).reshape(-1,context.shape[1],9,9)*mv
            decoded=self.up_middle[1](self.up_middle[0](torch.cat([skip,lower],1)))*mv
            decoded=self.up_middle[3](self.up_middle[2](decoded))*mv
            # Read the required 7x7 input without constructing a full-res decoder.
            pp=self.patch_xy+pos.long()[:,None,None,:];px,py=pp[...,0],pp[...,1]
            valid=((px>=0)&(px<w)&(py>=0)&(py<h))[:,None]
            ix=(py.clamp(0,h-1)*w+px.clamp(0,w-1)).flatten(1)
            fp=torch.gather(fine.flatten(2),2,ix[:,None].expand(-1,fine.shape[1],-1)).reshape(-1,fine.shape[1],7,7)*valid
            mx=torch.div(px.clamp(0,w-1)*mw,w,rounding_mode='floor');my=torch.div(py.clamp(0,h-1)*mh,h,rounding_mode='floor')
            mi=((my-center[:,1,None,None]+4)*9+mx-center[:,0,None,None]+4).flatten(1)
            mp=torch.gather(decoded.flatten(2),2,mi[:,None].expand(-1,decoded.shape[1],-1)).reshape(-1,decoded.shape[1],7,7)*valid
            patch=torch.cat([fp,mp],1)
            patch=self.up_fine[1](self.up_fine[0](patch))*valid
            patch=self.up_fine[3](self.up_fine[2](patch))*valid
            gl=self.readout(patch[:,:,2:5,2:5].flatten(1))
        return self.head(torch.cat([lo,gl,stats[:,:2]],1)).float().masked_fill(mask==0,-1e9)

class ThinSpatialPolicy(CroppedSpatialPolicy):
    """Full-resolution spatial encoder with fewer channels; requires retraining."""
    def __init__(self,arm='terrain',amp=True):
        super().__init__(arm,amp)
        def block(a,b):return nn.Sequential(nn.Conv2d(a,b,3,padding=1),nn.ReLU(),nn.Conv2d(b,b,3,padding=1),nn.ReLU())
        self.fine=block(13,8);self.middle=block(8,16);self.coarse=block(16,24)
        self.context=nn.Sequential(nn.Conv2d(24,24,3,padding=2,dilation=2),nn.ReLU(),nn.Conv2d(24,24,3,padding=2,dilation=2),nn.ReLU())
        self.up_middle=block(40,16);self.up_fine=block(24,8)
        self.readout=nn.Sequential(nn.Linear(8*9,128),nn.ReLU())

POLICIES={'conv':Policy,'spatial':SpatialPolicy,'packed':PackedPolicy,
          'packed2':Packed2Policy,'cropped':CroppedSpatialPolicy,'thin':ThinSpatialPolicy}
