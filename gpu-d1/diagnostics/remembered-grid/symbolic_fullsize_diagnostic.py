"""Separate global-map rescaling from the harder native navigation geometry.

The padded-global arm keeps small-map dynamics, local inputs, tactical inputs,
time, and actions unchanged. Only the global summary is recomputed on an 80x70
canvas, with the original 32x32 observations placed at their native offset.
Unobserved padding stays unknown. This is a diagnostic, not a proposed policy.
"""
import hashlib
import torch
from torch.nn import functional as F
from run import evaluate, save_json
from runtime import Env, OUT, ROOT, build
from fullsize_navigation import FullEnv, build_full
from optimize_symbolic import load
from symbolic_execution import PolicyExecution, StaticInference
from symbolic_policy import global_map, categories
from compact_policy import crop


class DiagnosticExecution(PolicyExecution):
    def __init__(self, model, intervention):
        super().__init__(model, compiled=True)
        self.intervention = intervention

    def features(self, g, s, prepared=None):
        local, glob, tactical, stats = self.model.prepare(g, s)
        if self.intervention == 'padded_global':
            assert g.shape[-2:] == (32, 32)
            padded = F.pad(g, (24, 24, 19, 19))
            shifted = s.clone()
            shifted[:, 2] += 24
            shifted[:, 3] += 19
            glob = self.model.prepare(padded, shifted)[1]
        x = self.encode((local, glob, tactical, stats))
        if self.intervention == 'erase_global':
            x = torch.cat([x[:, :64], torch.zeros_like(x[:, 64:160]), x[:, 160:]], -1)
        return x


def main():
    torch.set_num_threads(1)
    torch.backends.cudnn.benchmark = True
    build(); build_full()
    model = load(True).configure_encoder(True, True)
    env = FullEnv('validation', 8); env.reset(seed=913)
    # Independent/reference symbolic preprocessing on actual native observations.
    with torch.no_grad():
        local, glob, tactical, stats = model.prepare(env.grid, env.stats)
        reference = crop(torch.cat([categories(env.grid), (env.grid[:, 4:5] > 0).float()], 1), env.stats[:, 2:], model.offsets)
        reference[:, 1:2] += (reference[:, :4].sum(1, keepdim=True) == 0).float()
        assert torch.equal(local, reference)
        torch.testing.assert_close(glob, global_map(env.grid, env.stats), rtol=0, atol=0)
        torch.testing.assert_close(glob[:, :4].sum(1), torch.ones_like(glob[:, 0]), rtol=0, atol=1e-6)
        assert torch.equal(stats, env.stats[:, :2])
    report = dict(preprocessing_reference_passed=True, evaluations={})
    path = ROOT / 'results/symbolic-fullsize-diagnostic.json'
    arms = [
        ('small_source_normal', 'symbolic-ppo-durable-seed0', Env, 'normal', 256),
        ('small_source_padded_global', 'symbolic-ppo-durable-seed0', Env, 'padded_global', 256),
        ('small_source_erase_global', 'symbolic-ppo-durable-seed0', Env, 'erase_global', 256),
        ('full_source_normal', 'symbolic-ppo-durable-seed0', FullEnv, 'normal', 1024),
        ('full_source_erase_global', 'symbolic-ppo-durable-seed0', FullEnv, 'erase_global', 1024),
        ('full_1m_normal', 'symbolic-ppo-fullsize-seed0', FullEnv, 'normal', 1024),
        ('full_1m_erase_global', 'symbolic-ppo-fullsize-seed0', FullEnv, 'erase_global', 1024),
    ]
    for name, source, factory, intervention, limit in arms:
        checkpoint = OUT / source / 'latest.pt'
        model = load(True).configure_encoder(True, True)
        model.load_state_dict(torch.load(checkpoint, weights_only=False)['model'])
        policy = StaticInference(DiagnosticExecution(model, intervention), amp=True, graphed=True)
        torch.manual_seed(11812)
        result = evaluate(policy, 'test', env_class=factory, limit=limit)
        result['source_sha256'] = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        report['evaluations'][name] = result
        save_json(path, report)
        print(name, result['summary'], flush=True)
        del policy, model
    report['finished'] = True
    save_json(path, report)


if __name__ == '__main__':
    main()
