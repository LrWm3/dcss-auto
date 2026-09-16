"""Evaluate fixed turn-trained weights under alternate deadlines; no training."""
import argparse
import json
import pathlib
import time

import torch
from torch import nn
from torch.distributions import Categorical

from learn_env_ring_multi import Env
from run_ring_ablations import digest, library_key, corpus_manifest


class Policy(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(958, width), nn.Tanh(), nn.Linear(width, width), nn.Tanh())
        self.actor, self.critic = nn.Linear(width, 10), nn.Linear(width, 1)

    def forward(self, obs, mask):
        return Categorical(logits=self.actor(self.body(obs)).masked_fill(mask == 0, -1e9))


@torch.no_grad()
def evaluate(model, env, mode, physical_clock):
    env.reset(900000)
    active = torch.ones(env.batch, dtype=torch.bool, device='cuda')
    terminal = torch.zeros_like(env.out)
    decisions = torch.zeros(env.batch, device='cuda')
    turns = torch.zeros_like(decisions)
    reward = torch.zeros_like(decisions)
    travel_turns = torch.zeros_like(decisions)
    travel_uses = torch.zeros_like(decisions)
    torch.manual_seed(900000)
    for _ in range(512):
        if physical_clock:
            # Preserve the training clock's units, allowing values >1 beyond
            # the old deadline. This explicitly tests an out-of-range input.
            env.obs[:, 651] = turns / 512
        dist = model(env.obs, env.mask)
        action = dist.sample() if mode == 'sampled' else dist.probs.argmax(-1)
        _, out = env.step(action, active=active)
        reward += active * out[:, 0]
        turns += active * out[:, 26]
        decisions += active
        travel_turns += active * out[:, 28]
        travel_uses += active * out[:, 27]
        ended = active & (out[:, 1] > 0)
        terminal[ended] = out[ended]
        active &= ~ended
    assert not active.any().item()
    assert torch.equal(turns, terminal[:, 5])

    def metrics(index):
        t = terminal[index]
        return dict(clear_rate=t[:, 2].mean().item(), death_rate=t[:, 6].mean().item(),
                    timeout_rate=t[:, 7].mean().item(), kills=t[:, 3].mean().item(),
                    floor_coverage=t[:, 11].mean().item(), turns=turns[index].mean().item(),
                    policy_decisions=decisions[index].mean().item(),
                    shaped_return=reward[index].mean().item(),
                    travel_turns=travel_turns[index].mean().item(),
                    travel_uses=travel_uses[index].mean().item())

    result = metrics(slice(None))
    result['maps'] = {str(m['seed']): metrics(slice(i, None, len(env.metadata)))
                      for i, m in enumerate(env.metadata)}
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--suite', type=pathlib.Path, required=True)
    ap.add_argument('--output', type=pathlib.Path, required=True)
    args = ap.parse_args()
    torch.set_num_threads(1)
    torch.backends.cuda.matmul.allow_tf32 = False
    manifest = json.loads((args.suite/'manifest.json').read_text())
    corpus = pathlib.Path(manifest['corpus'])
    assert corpus_manifest(corpus) == manifest['maps']
    jobs = {j['decision_limit']: j for j in manifest['jobs']}
    source = args.suite/'runs'/jobs[False]['id']/'latest.pt'
    saved = torch.load(source, map_location='cpu', weights_only=False)
    assert saved['job'] == jobs[False]
    model = Policy(jobs[False]['width']).cuda().eval()
    model.load_state_dict(saved['model'])
    report = dict(checkpoint_sha256=digest(source), source_decisions=saved['decisions'],
                  source_train_seconds=saved['train_seconds'], training_performed=False,
                  script_sha256=digest(pathlib.Path(__file__)), evaluations={})
    start = time.perf_counter()
    for label, decision_limit, physical_clock in [
            ('original_turn_deadline', False, False),
            ('decision_deadline_decision_clock', True, False),
            ('decision_deadline_physical_clock', True, True)]:
        job = jobs[decision_limit]
        lib = args.suite/'build'/(library_key(job)+'.so')
        assert digest(lib) == lib.with_suffix('.sha256').read_text().strip()
        env = Env(batch=1024, enemies=24, seed=900000, corpus=corpus/'validation',
                  map_limit=32, map_filter=-2, library_path=lib, limit=512)
        results = {mode: evaluate(model, env, mode, physical_clock) for mode in ['sampled', 'greedy']}
        if not decision_limit:
            original = json.loads((source.parent/'result.json').read_text())['final']
            for mode in results:
                for key in ['clear_rate', 'death_rate', 'timeout_rate', 'kills', 'floor_coverage', 'turns']:
                    assert results[mode][key] == original[mode][key], (mode, key)
        report['evaluations'][label] = dict(library_sha256=digest(lib), **results)
        print(label, json.dumps({k:v for k,v in results['sampled'].items() if k!='maps'}), flush=True)
        del env
    assert digest(source) == report['checkpoint_sha256']
    report['evaluation_seconds'] = time.perf_counter()-start
    args.output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
