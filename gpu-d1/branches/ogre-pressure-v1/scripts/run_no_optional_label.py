"""Fresh two-ogre baseline with only the explicit required/optional bit masked.

Separate entry point preserves the source manifest of the running baseline.
Supports --after-suite PATH to wait for a completed preceding suite.
"""
import sys
import run_ring_ablations as runner
import learn_env_ring_multi as environment

OriginalEnv = environment.Env

class NoOptionalLabelEnv(OriginalEnv):
    def hide_label(self):
        # Fixed 741-wide ogre schema: 421 + monster slot * 8 is the
        # kill-required bit. Keep width/order and all other fields intact.
        assert self.obs.shape[1] == 741
        self.obs[:, 421::8] = 0
        return self.obs

    def reset(self, seed):
        super().reset(seed)
        return self.hide_label()

    def step(self, actions, active=None):
        _, out = super().step(actions, active=active)
        return self.hide_label(), out


def main():
    environment.Env = NoOptionalLabelEnv
    runner.VARIANTS = {'ogre2_no_optional_label': dict(runner.VARIANTS['ogre2_base'], no_optional_label=True)}
    runner.DEFAULT = 'ogre2_no_optional_label'
    runner.SOURCE_FILES = [*runner.SOURCE_FILES, 'scripts/run_no_optional_label.py']
    # Worker subprocesses must re-enter this wrapper so masking applies there.
    runner.__file__ = __file__
    if '--after-suite' in sys.argv:
        import queue_after
        return queue_after.main()
    return runner.main()


if __name__ == '__main__':
    sys.exit(main())
