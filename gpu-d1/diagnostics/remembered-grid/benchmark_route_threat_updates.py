"""Compare equivalent recurrence/update implementations on a fixed PPO rollout."""
import copy,json,time
import torch
from route_threat_ppo import PPO,FastAgent,ThreatEnv,FOLDER_OUT,ROOT,collect,update,save_json
from route_threat_fast import GraphInference
from benchmark_route_threat import timing


def main():
    torch.set_num_threads(1);torch.manual_seed(0);torch.backends.cudnn.benchmark=True
    source=FOLDER_OUT/'route-threat-visible/selected.pt'
    base=PPO(source);base.inference=GraphInference(base)
    env=ThreatEnv('train',32);env.reset(40000);agent=FastAgent(base.actor,False)
    data,metrics=collect(env,agent,base)
    initial=copy.deepcopy(base.state_dict());x,mask,actions,oldlp,adv,ret=[t[:64] for t in data]
    result={'rollout':metrics,'variants':{},'note':'Fixed rollout; identical initial weights, optimizer, RNG, and PPO settings. Compilation cost reported separately.'}
    # FP32 equivalence includes input projection gradients across all 20 steps.
    base.actor.hoist_inputs=False;base.zero_grad(set_to_none=True)
    y=base.actor(x.float());loss=y.square().mean();loss.backward()
    gradients={n:p.grad.clone() for n,p in base.actor.named_parameters() if p.grad is not None};reference=y.detach()
    base.actor.hoist_inputs=True;base.zero_grad(set_to_none=True)
    y=base.actor(x.float());y.square().mean().backward()
    torch.testing.assert_close(y,reference,atol=2e-5,rtol=2e-4)
    for n,p in base.actor.named_parameters():
        if n in gradients:torch.testing.assert_close(p.grad,gradients[n],atol=2e-5,rtol=2e-3)
    result['hoist_fp32_forward_and_gradients_pass']=True
    for variant in ['eager','hoisted','compiled','hoisted_compiled']:
        model=PPO(source);model.load_state_dict(initial);model.actor.hoist_inputs='hoisted' in variant
        opt=torch.optim.Adam([{'params':model.actor.parameters(),'lr':1e-5},{'params':model.value.parameters(),'lr':1e-4}]);scaler=torch.amp.GradScaler('cuda',init_scale=1024)
        model.inference=GraphInference(model)
        if 'compiled' in variant:model.compiled_raw=torch.compile(model.raw,fullgraph=True)
        t=time.perf_counter()
        dist,v=model(x,mask);loss=-(dist.log_prob(actions)*adv).mean()+.25*(v-ret).square().mean();loss.backward();torch.cuda.synchronize()
        warmup=time.perf_counter()-t
        actual_grad={n:p.grad.detach().clone() for n,p in model.named_parameters() if p.grad is not None}
        reference_model=PPO(source);reference_model.load_state_dict(initial)
        rd,rv=reference_model(x,mask)
        (-(rd.log_prob(actions)*adv).mean()+.25*(rv-ret).square().mean()).backward()
        numerator=sum((actual_grad[n]-p.grad).float().square().sum() for n,p in reference_model.named_parameters() if p.grad is not None)
        denominator=sum(p.grad.float().square().sum() for p in reference_model.parameters() if p.grad is not None)
        grad_error=float((numerator/denominator.clamp_min(1e-20)).sqrt())
        assert grad_error<.02,grad_error
        del reference_model,actual_grad
        model.zero_grad(set_to_none=True)
        with torch.no_grad():
            logits,_=getattr(model,'compiled_raw',model.raw)(x,mask)
            ref=PPO(source);ref.load_state_dict(initial);expected,_=ref.raw(x,mask)
            error=float((logits[mask]-expected[mask]).abs().max())
            torch.testing.assert_close(logits[mask],expected[mask],atol=.01,rtol=.005)
            del ref
        def backward():
            model.zero_grad(set_to_none=True)
            dist,v=model(x,mask);loss=-(dist.log_prob(actions)*adv).mean()+.25*(v-ret).square().mean();loss.backward()
        fb=timing(backward,n=30)
        trials=[]
        for repeat in range(3):
            model.load_state_dict(initial);opt.state.clear();scaler=torch.amp.GradScaler('cuda',init_scale=1024);torch.manual_seed(123)
            torch.cuda.synchronize();t=time.perf_counter();stats=update(model,opt,scaler,data);torch.cuda.synchronize()
            trials.append({'seconds':time.perf_counter()-t,**stats})
        result['variants'][variant]={'first_forward_backward_seconds':warmup,'forward_backward_ms':fb,'amp_max_valid_logit_error':error,'gradient_relative_l2_error':grad_error,'trials':trials}
        model.load_state_dict(initial);opt.state.clear();scaler=torch.amp.GradScaler('cuda',init_scale=1024);torch.manual_seed(456)
        env.reset(40000);learner=FastAgent(model.actor,False);waves=[]
        for _ in range(4):
            torch.cuda.synchronize();t=time.perf_counter();rollout,counts=collect(env,learner,model)
            diagnostic=update(model,opt,scaler,rollout);torch.cuda.synchronize()
            waves.append(dict(seconds=time.perf_counter()-t,**counts,**diagnostic));del rollout
        result['variants'][variant]['end_to_end_rollouts']=waves
        save_json(ROOT/'results/route-threat-update-performance.json',result);print(variant,json.dumps(result['variants'][variant]),flush=True)
        del model,opt
    print('DONE',flush=True)

if __name__=='__main__':main()
