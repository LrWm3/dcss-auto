"""Illustrate that small final displacement can hide substantial random wandering."""
import json,pathlib
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=pathlib.Path(__file__).resolve().parents[2]
r=json.loads((ROOT/'results/centered-map-random-uniform.json').read_text())
t=np.load(ROOT/'learning-runs/centered-map-random-audit/uniform-traces.npz')['trace']
m=json.loads((ROOT/'learning-runs/vision15-centered-map/manifest.json').read_text())
fig,axs=plt.subplots(1,3,figsize=(14,5),layout='constrained')
for ax,(ix,limit) in zip(axs,[(0,64),(0,2048),(1,2048)]):
 e=r['examples'][ix];raw=(pathlib.Path(m['corpus'])/'validation'/f"map-{e['map_seed']}.bin").read_bytes()
 floor=np.frombuffer(raw,np.uint8,count=5600,offset=28).reshape(70,80)
 ax.imshow(floor,cmap='Greys_r',vmin=-.4,vmax=1.15,interpolation='nearest')
 tr=t[:limit,ix];tr=tr[tr[:,5]>0];path=np.vstack([e['start'],tr[:,:2]])
 ax.plot(path[:,0],path[:,1],color='#1688ba',lw=.8,alpha=.65)
 ax.scatter(*e['start'],color='#21a355',s=65,marker='o',label='Start',zorder=5)
 ax.scatter(*path[-1],color='#c72c41',s=75,marker='x',label='End',zorder=6)
 events=[v for v in e['kill_events'] if v['decision']<=limit]
 if events:
  k=np.array([v['player'] for v in events]);ax.scatter(k[:,0],k[:,1],s=50,marker='*',color='#f4a700',label='Kill location',zorder=4)
 yy,xx=np.where(floor);ax.set_xlim(xx.min()-2,xx.max()+2);ax.set_ylim(yy.max()+2,yy.min()-2)
 unique=len(np.unique(path,axis=0));distance=np.abs(path[-1]-path[0]).max()
 ax.set_title(f"Episode {ix}, first {len(tr):,} decisions\n{len(events)} kills · {unique} occupied tiles\nEnds {distance} tiles from start",fontsize=10)
 ax.set_aspect('equal');ax.set_xlabel('Tile x');ax.set_ylabel('Tile y')
axs[0].legend(loc='upper left',fontsize=8)
fig.suptitle('Uniform random legal actions: wandering and enemies approaching can produce kills',fontsize=12)
fig.savefig(ROOT/'results/centered-map-random-paths.png',dpi=150)
