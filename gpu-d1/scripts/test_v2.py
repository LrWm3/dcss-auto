"""Semantic and CPU/CUDA parity checks for the v2 task."""
import argparse
import pathlib
import sys
import torch
from learn_env_v2 import EnvV2, ROOT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', type=pathlib.Path, default=ROOT / 'fixtures/v2-corpus')
    ap.add_argument('--batch', type=int, default=37)
    ap.add_argument('--steps', type=int, default=900)
    args = ap.parse_args()
    torch.set_num_threads(1)
    cpu = EnvV2(args.batch, 8, seed=91, device='cpu', limit=512, corpus=args.corpus)
    gpu = EnvV2(args.batch, 8, seed=91, device='cuda', limit=512, corpus=args.corpus)
    assert torch.equal(cpu.obs, gpu.obs.cpu())
    assert (cpu.obs[:, 169] == 0).all(), 'all monsters must begin asleep'
    seen_maps = set()
    for k in range(args.steps):
        actions = (cpu.heuristic().clone() if k % 3 else
                   torch.randint(0, 9, (args.batch,), dtype=torch.int64))
        cpu.step(actions); gpu.step(actions.cuda())
        assert torch.equal(cpu.obs, gpu.obs.cpu()), ('obs', k)
        assert torch.equal(cpu.mask, gpu.mask.cpu()), ('mask', k)
        assert torch.equal(cpu.out, gpu.out.cpu()), ('out', k)
        seen_maps.update(int(x) for x in cpu.out[:, 10].tolist())
        assert torch.all((cpu.out[:, 3] >= 0) & (cpu.out[:, 3] <= 8))
        assert torch.all((cpu.out[:, 4] >= 0) & (cpu.out[:, 4] <= 34))
        assert torch.all((cpu.out[:, 8] >= 0) & (cpu.out[:, 8] <= 8))
        assert torch.all((cpu.out[:, 9] >= 0))
        assert torch.all((cpu.out[:, 10] >= 0) & (cpu.out[:, 10] < len(cpu.metadata)))
    if len(cpu.metadata) == 6:
        assert len(seen_maps) == 6, seen_maps
    # The variable statistics are present numerically and include the strong/slow archetype.
    stats = cpu.obs[:, 162:242]
    assert (stats[:, 13] > .5).any(), 'strong/slow damage feature missing'
    assert (stats[:, 15] < .4).any(), 'slow speed feature missing'
    player = cpu.obs[:, 242:247]
    assert player[:, 1].unique().numel() > 1, 'player HP variation is not exposed'
    assert player[:, 3].unique().numel() > 1, 'player damage variation is not exposed'
    heldout = EnvV2(19, 8, seed=2718, device='cpu', limit=64, corpus=args.corpus,
                    stat_mode=2, player_mode=2)
    assert (heldout.obs[:, 162:242][:, 13] > .7).any(), 'held-out strong/slow stats missing'
    assert heldout.obs[:, 243].min() <= .75 and heldout.obs[:, 243].max() > .95, 'held-out player range missing'
    print(f'PASS v2: {args.batch} worlds x {args.steps} transitions, exact CPU/CUDA parity, '
          f'{len(cpu.metadata)} maps, sleep, stats, resets')


if __name__ == '__main__': main()
