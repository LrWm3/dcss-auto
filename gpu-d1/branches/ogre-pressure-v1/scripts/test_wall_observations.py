"""CPU/CUDA parity and observation-activity checks for corrected wall variants."""
import torch
import learn_env_sleep as backend


def main():
    torch.set_num_threads(1)
    torch.manual_seed(91)
    for name, size in [('ring', 246), ('frontier_memory', 213)]:
        backend._LIB = None
        backend.LIB_NAME = f'learn_sleep_explore_{name}_walls.so'
        cpu = backend.Env(37, 8, seed=91, device='cpu')
        gpu = backend.Env(37, 8, seed=91, device='cuda')
        assert cpu.obs.shape == (37, size)
        active = False
        values = set()
        for step in range(302):
            assert torch.equal(cpu.obs, gpu.obs.cpu()), ('obs', name, step)
            assert torch.equal(cpu.mask, gpu.mask.cpu()), ('mask', name, step)
            assert torch.equal(cpu.state, gpu.state.cpu()), ('state', name, step)
            if step:
                assert torch.equal(cpu.out, gpu.out.cpu()), ('out', name, step)
            active |= bool(cpu.obs[:, 206].any())
            values.update(cpu.obs[:, 206:].unique().tolist())
            if step == 301:
                break
            actions = cpu.heuristic().clone() if step % 2 == 0 else torch.randint(0, 9, (37,))
            cpu.step(actions)
            gpu.step(actions.cuda())
        assert active, f'{name}: observation extension never active'
        if name == 'ring':
            assert values == {-1., 0., 1.}, values
        print(f'PASS {name}: 37 worlds x 301 actions; exact CPU/CUDA parity and active inputs')


if __name__ == '__main__':
    main()
