"""Terminal, padding and sequence order checks independent of the simulator."""
import torch
from symbolic_ppo import gae_returns, sequences

# Episode A succeeds at t=1, episode B dies at t=0; padded values must
# neither bootstrap terminal rewards nor leak back into live advantages.
r=torch.tensor([[0.,-1.],[1.,0.],[0.,0.]])
v=torch.tensor([[.2,.3],[.4,17.],[99.,123.]])
d=torch.tensor([[False,True],[True,False],[False,False]])
a=torch.tensor([[True,True],[True,False],[False,False]])
adv,ret=gae_returns(r,v,d,a,gamma=.9,lam=.8)
torch.testing.assert_close(adv,torch.tensor([[.592,-1.3],[.6,0.],[0.,0.]]))
torch.testing.assert_close(ret[a],torch.tensor([.792,-1.,1.]))
x=torch.arange(32*3).reshape(32,3)
s=sequences(x)
for env in range(3):
 for chunk in range(2):torch.testing.assert_close(s[env*2+chunk],x[chunk*16:(chunk+1)*16,env])
print('PASS terminal GAE, inactive padding, chronological per-environment sequences')
# Lambda=1 must give complete discounted episode returns, independent of
# inaccurate value predictions (the diagnostic deliberately varies them).
_,mc=gae_returns(r,v,d,a,gamma=.9,lam=1.)
_,mc2=gae_returns(r,v*7-3,d,a,gamma=.9,lam=1.)
expected=torch.tensor([.9,-1.,1.])
torch.testing.assert_close(mc[a],expected)
torch.testing.assert_close(mc2[a],expected)
print('PASS lambda=1 returns independent of value predictions')
