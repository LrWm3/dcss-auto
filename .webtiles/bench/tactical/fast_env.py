"""Experimental FIFO observations with PTY actions; not a headless engine.

Use in separate worker processes: launch temporarily sets the child environment.
Historical adapters, checkpoints and full-transition logging remain unchanged.
"""
import json
import os
import re
import select
import shutil
import tempfile
import time
from pathlib import Path

import pexpect
import bench
from goal_env import GoalEnvironment, GOAL_ACTIONS

FIFO_ENV = 'DCSS_TACTICAL_OBSERVATION_FIFO'

def derive_fast(case, destination):
    case, destination = Path(case), Path(destination)
    meta = json.loads((case/'case.json').read_text())
    for name, key in [('checkpoint.cs','save_sha256'), ('trial.rc','rc_sha256')]:
        if bench.sha(case/name) != meta[key]:
            raise ValueError('Parent checksum mismatch')
    source = (case/'trial.rc').read_text()
    replacements = {
        '  crawl.dump_char()\n  crawl.mpr("TBREADY "..TB.seq.." END")':
            '  crawl.tactical_emit(tactical_dump)',
        '  crawl.mpr("TBACCEPT END")': '  -- No terminal acknowledgement needed.',
        '    crawl.redraw_screen()': '    -- Explicit per-decision redraw omitted.',
    }
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError('Unrecognized bridge: '+old)
        source = source.replace(old, new)
    destination.mkdir(parents=True, exist_ok=False)
    shutil.copy2(case/'checkpoint.cs', destination/'checkpoint.cs')
    (destination/'trial.rc').write_text(source)
    meta.update(parent_case=str(case.resolve()), parent_engine_sha256=meta['engine_sha256'],
                parent_rc_sha256=meta['rc_sha256'], engine_sha256=bench.sha(bench.ENGINE),
                rc_sha256=bench.sha(destination/'trial.rc'), training_ready=False,
                transport='fifo-v1', transport_adapter_sha256=bench.sha(Path(__file__)))
    (destination/'case.json').write_text(json.dumps(meta, indent=2)+'\n')
    return destination

class FastEnvironment(GoalEnvironment):
    def launch(self, checkpoint=None):
        if checkpoint is None:
            raise ValueError('Fast adapter currently requires a derived checkpoint')
        self.close()
        self.pipe_dir = Path(tempfile.mkdtemp(prefix='fifo-', dir=self.workspace))
        fifo = self.pipe_dir/'observations'
        os.mkfifo(fifo, 0o600)
        # RDWR keeps a reader present across emits and avoids artificial EOFs.
        self.pipe_fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
        self.buffer = b''
        previous = os.environ.get(FIFO_ENV)
        os.environ[FIFO_ENV] = str(fifo)
        self.launching = True  # Parent launch calls close() before spawning.
        try:
            state = super().launch(checkpoint)
            manifest = json.loads((self.work/'run.json').read_text())
            manifest.update(transport='fifo-v1', fast_adapter_sha256=bench.sha(Path(__file__)),
                            event_schema='initial_then_next_v1')
            (self.work/'run.json').write_text(json.dumps(manifest, indent=2)+'\n')
            self.events = (self.work/'events.jsonl').open('w')
            self.events.write(json.dumps({'initial_observation':state})+'\n')
            return state
        except Exception:
            self.launching = False
            self.close()
            raise
        finally:
            self.launching = False
            if previous is None:
                os.environ.pop(FIFO_ENV, None)
            else:
                os.environ[FIFO_ENV] = previous

    def await_state(self, startup=False, expected_seq=None):
        self.child.delaybeforesend = None
        self.child.logfile_read = None
        deadline = time.monotonic() + (600 if startup else 20)
        terminal = ''
        while time.monotonic() < deadline:
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                if not line:
                    continue
                if not line.startswith(b'TBJSON '):
                    raise RuntimeError('Invalid FIFO frame')
                state = json.loads(line[7:])
                if expected_seq is not None and state['seq'] != expected_seq:
                    raise RuntimeError('Out-of-order observation')
                self.state = state
                return state
            ready, _, _ = select.select([self.pipe_fd, self.child.child_fd], [], [], .1)
            if self.pipe_fd in ready:
                self.buffer += os.read(self.pipe_fd, 262144)
            if self.child.child_fd in ready:
                try:
                    data = self.child.read_nonblocking(65536, timeout=0)
                    terminal = (terminal + data)[-8192:]
                    # Keep a bounded diagnostic tail, not a full rendering log.
                    self.terminal_tail = terminal
                    if startup and re.search(r'(?:Hit|Press) .* to (?:continue|start)', terminal):
                        self.child.send(' ')
                        terminal = ''
                except pexpect.TIMEOUT:
                    pass
                except pexpect.EOF:
                    death = self.death_record()
                    if death:
                        return death
                    raise RuntimeError('Unexpected engine exit: '+terminal[-1000:])
            if not startup and ('You die' in terminal or not ready):
                death = self.death_record()
                if death:
                    return death
        raise TimeoutError(f'No FIFO boundary (not a death); see {self.work}')

    def step(self, action):
        if action not in GOAL_ACTIONS:
            raise ValueError(action)
        before = self.state
        if before.get('terminal'):
            raise RuntimeError('Terminal episode')
        self.child.send(chr(97 + list(GOAL_ACTIONS).index(action)))
        after = self.await_state(expected_seq=before['seq']+1)
        self.state = after
        # Initial state once, then each next state once. Flush on close.
        self.events.write(json.dumps(dict(action=action, before_seq=before['seq'],
            next_observation=after, terminated=after.get('terminal')=='death'))+'\n')
        return after

    def close(self):
        if getattr(self, 'launching', False):
            return
        try:
            super().close()
        finally:
            if getattr(self, 'events', None):
                self.events.close()
                self.events = None
            if hasattr(self, 'pipe_fd'):
                os.close(self.pipe_fd)
                del self.pipe_fd
                (self.pipe_dir/'observations').unlink()
                self.pipe_dir.rmdir()
            if getattr(self, 'terminal_tail', None) and hasattr(self, 'work'):
                (self.work/'terminal-tail.txt').write_text(self.terminal_tail)
