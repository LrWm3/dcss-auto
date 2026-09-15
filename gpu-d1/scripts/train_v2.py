#!/usr/bin/env python3
"""PPO on the multi-layout, sleeping/variable-statistics proxy task."""
import argparse, hashlib, json, math, pathlib, platform, time
import torch
from torch import nn
from torch.distributions import Categorical, Distribution
from learn_env_v2 import EnvV2, ROOT

Distribution.set_default_validate_args(False)


class Policy(nn.Module):
    def __init__(self, obs=250):
        super().__init__()
        self.body = nn.Sequential(nn.Linear(obs, 160), nn.Tanh(), nn.Linear(160, 160), nn.Tanh())
        self.actor, self.critic = nn.Linear(160, 9), nn.Linear(160, 1)
        for layer in self.modules():
            if isinstance(layer, nn.Linear): nn.init.orthogonal_(layer.weight, math.sqrt(2)); nn.init.zeros_(layer.bias)
        nn.init.orthogonal_(self.actor.weight, .01); nn.init.orthogonal_(self.critic.weight, 1)

    def forward(self, obs, mask):
        h = self.body(obs)
        return Categorical(logits=self.actor(h).masked_fill(mask == 0, -1e9)), self.critic(h).squeeze(-1)


@torch.no_grad()
def evaluate(env, policy=None, mode='greedy', seed=900000):
    env.reset(seed)
    active = torch.ones(env.batch, dtype=torch.bool, device=env.device)
    terminal = torch.zeros((env.batch, 12), device=env.device)
    returns = torch.zeros(env.batch, device=env.device)
    with torch.random.fork_rng(devices=[env.device.index]):
        torch.manual_seed(seed)
        for _ in range(env.limit):
            if mode == 'wait': a = torch.full((env.batch,), 8, dtype=torch.int64, device=env.device)
            elif mode == 'random': a = torch.multinomial(env.mask, 1).squeeze(1)
            elif mode == 'pursuit': a = env.heuristic()
            else:
                dist, _ = policy(env.obs, env.mask)
                a = dist.probs.argmax(-1) if mode == 'greedy' else dist.sample()
            _, out = env.step(a)
            returns += out[:, 0] * active
            ended = active & (out[:, 1] > 0)
            terminal[ended] = out[ended]
            active &= ~ended
    assert not active.any().item()
    t = terminal.cpu().numpy(); n = env.batch; successes = float(t[:, 2].sum()); p = successes / n; z = 1.96
    center = (p + z*z/(2*n))/(1 + z*z/n); half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/(1 + z*z/n)
    return dict(mode=mode, eval_seed=seed, episodes=n, clear_rate=p, clear_ci95=[center-half, center+half],
                enemies_killed=float(t[:, 3].mean()), killed_fraction=float(t[:, 3].mean()/env.enemies),
                mean_hp=float(t[:, 4].mean()), mean_length=float(t[:, 5].mean()),
                clear_length=float(t[t[:, 2] > 0, 5].mean()) if successes else None,
                death_rate=float(t[:, 6].mean()), timeout_rate=float(t[:, 7].mean()),
                mean_awake=float(t[:, 8].mean()), mean_damage_taken=float(t[:, 9].mean()),
                map_counts={str(int(k)): int((t[:, 10] == k).sum()) for k in sorted(set(t[:, 10]))},
                mean_return=float(returns.mean().item()))


def emit(path, row):
    with path.open('a') as f: f.write(json.dumps(row, allow_nan=False) + '\n')
    print(json.dumps(row, allow_nan=False), flush=True)


def train(args, seed, eval_env):
    torch.manual_seed(seed); env = EnvV2(args.batch, args.enemies, seed=seed*100000+17, limit=args.limit,
                                          corpus=args.train_corpus, sleep_radius=args.sleep_radius,
                                          stat_mode=args.stat_mode, player_mode=args.player_mode)
    model = Policy().cuda(); opt = torch.optim.Adam(model.parameters(), lr=args.lr, eps=1e-5)
    folder = args.output / f'seed-{seed}'; folder.mkdir(parents=True, exist_ok=False); log = folder/'curve.jsonl'
    T, B = args.horizon, args.batch; total = train_seconds = collect_seconds = update_seconds = update = 0
    obs = torch.empty((T, B, 250), device='cuda'); masks = torch.empty((T, B, 9), device='cuda')
    actions = torch.empty((T, B), dtype=torch.int64, device='cuda'); oldlp = torch.empty((T, B), device='cuda')
    values = torch.empty_like(oldlp); rewards = torch.empty_like(oldlp); dones = torch.empty_like(oldlp)
    advantages = torch.empty_like(oldlp); flatobs = obs.flatten(0, 1); flatmask = masks.flatten(0, 1); flata = actions.flatten()
    checks = [x for x in (100000, 300000, 1000000, 3000000, args.steps) if x <= args.steps]

    def checkpoint():
        row = dict(seed=seed, decisions=total, updates=update, train_seconds=train_seconds,
                   collection_seconds=collect_seconds, update_seconds=update_seconds,
                   decisions_per_second=total/train_seconds if train_seconds else None,
                   greedy=evaluate(eval_env, model, 'greedy'), sampled=evaluate(eval_env, model, 'sampled'))
        emit(log, row); torch.save({'model': model.state_dict(), 'optimizer': opt.state_dict(), 'decisions': total, 'seed': seed},
                                  folder / f'policy-{total}.pt')
    checkpoint()
    while total < args.steps:
        torch.cuda.synchronize(); begin = time.perf_counter()
        with torch.no_grad():
            for t in range(T):
                obs[t].copy_(env.obs); masks[t].copy_(env.mask); dist, v = model(env.obs, env.mask); a = dist.sample()
                actions[t], oldlp[t], values[t] = a, dist.log_prob(a), v; _, out = env.step(a)
                rewards[t], dones[t] = out[:, 0], out[:, 1]
            _, nextv = model(env.obs, env.mask); gae = torch.zeros(B, device='cuda')
            for t in reversed(range(T)):
                live = 1 - dones[t]; delta = rewards[t] + args.gamma * nextv * live - values[t]
                gae = delta + args.gamma * args.gae_lambda * live * gae; advantages[t], nextv = gae, values[t]
            returns = (advantages + values).flatten(); adv = advantages.flatten(); adv = (adv - adv.mean())/(adv.std()+1e-8)
        torch.cuda.synchronize(); collected = time.perf_counter() - begin
        begin = time.perf_counter()
        for _ in range(args.epochs):
            for inds in torch.randperm(T*B, device='cuda').split(args.minibatch):
                dist, v = model(flatobs[inds], flatmask[inds]); ratio = (dist.log_prob(flata[inds]) - oldlp.flatten()[inds]).exp()
                pg = -torch.minimum(ratio*adv[inds], ratio.clamp(.8, 1.2)*adv[inds]).mean()
                loss = pg + .25*(v-returns[inds]).square().mean() - args.entropy*dist.entropy().mean()
                opt.zero_grad(set_to_none=True); loss.backward(); nn.utils.clip_grad_norm_(model.parameters(), .5); opt.step()
        torch.cuda.synchronize(); learned = time.perf_counter() - begin
        collect_seconds += collected; update_seconds += learned; train_seconds += collected + learned
        total += T*B; update += 1
        if checks and total >= checks[0]: checks.pop(0); checkpoint()
    return model


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--output', type=pathlib.Path, required=True)
    ap.add_argument('--train-corpus', type=pathlib.Path, default=ROOT/'fixtures/v2-corpus')
    ap.add_argument('--eval-corpus', type=pathlib.Path); ap.add_argument('--steps', type=int, default=1000000)
    ap.add_argument('--seeds', default='0,1,2'); ap.add_argument('--batch', type=int, default=512)
    ap.add_argument('--horizon', type=int, default=64); ap.add_argument('--eval-episodes', type=int, default=1024)
    ap.add_argument('--enemies', type=int, default=8); ap.add_argument('--limit', type=int, default=512)
    ap.add_argument('--sleep-radius', type=int, default=6); ap.add_argument('--stat-mode', type=int, default=1)
    ap.add_argument('--player-mode', type=int, default=1); ap.add_argument('--lr', type=float, default=3e-4)
    ap.add_argument('--eval-stat-mode', type=int); ap.add_argument('--eval-player-mode', type=int)
    ap.add_argument('--gamma', type=float, default=.99); ap.add_argument('--gae-lambda', type=float, default=.95)
    ap.add_argument('--entropy', type=float, default=.01); ap.add_argument('--epochs', type=int, default=4)
    ap.add_argument('--minibatch', type=int, default=4096)
    args = ap.parse_args(); torch.set_num_threads(1); torch.backends.cuda.matmul.allow_tf32 = False
    args.output.mkdir(parents=True, exist_ok=False); eval_corpus = args.eval_corpus or args.train_corpus
    arg_meta = {k: (str(v) if isinstance(v, pathlib.Path) else v) for k, v in vars(args).items()}
    meta = arg_meta | {'output': str(args.output), 'torch': torch.__version__, 'gpu': torch.cuda.get_device_name(),
                          'platform': platform.platform(), 'task': 'multi-map sleep + explicit stats',
                          'sources': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                      [ROOT/'src/learn_v2.cu', ROOT/'scripts/learn_env_v2.py', pathlib.Path(__file__)]}}
    (args.output/'config.json').write_text(json.dumps(meta, indent=2) + '\n')
    eval_env = EnvV2(args.eval_episodes, args.enemies, seed=900000, limit=args.limit, corpus=eval_corpus,
                     sleep_radius=args.sleep_radius,
                     stat_mode=args.stat_mode if args.eval_stat_mode is None else args.eval_stat_mode,
                     player_mode=args.player_mode if args.eval_player_mode is None else args.eval_player_mode)
    for mode in ('wait', 'random', 'pursuit'): emit(args.output/'baselines.jsonl', evaluate(eval_env, mode=mode))
    for seed in map(int, args.seeds.split(',')): train(args, seed, eval_env)


if __name__ == '__main__': main()
