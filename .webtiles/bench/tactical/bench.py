"""Isolated, checkpoint-based Crawl tactical environment. Requires pexpect."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

import pexpect

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
ENGINE = Path(os.environ.get('DCSS_TACTICAL_ENGINE',
    str(ROOT / 'crawl-0.35/crawl-ref/source/crawl-observation-rng'))).resolve()
RC = ROOT / '.webtiles/rcs/codex-autocrawl.rc'
NAME = 'TacticalEustachio'
SEED = '1760771545328102746'
ACTIONS = {'baseline': 'baseline', 'wait': 'CMD_WAIT', 'tab': 'CMD_AUTOFIGHT',
           'melee': 'CMD_AUTOFIGHT_NOMOVE', 'berserk': 'berserk',
           'n': 'CMD_MOVE_UP', 's': 'CMD_MOVE_DOWN', 'w': 'CMD_MOVE_LEFT',
           'e': 'CMD_MOVE_RIGHT', 'nw': 'CMD_MOVE_UP_LEFT',
           'ne': 'CMD_MOVE_UP_RIGHT', 'sw': 'CMD_MOVE_DOWN_LEFT',
           'se': 'CMD_MOVE_DOWN_RIGHT'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_rc(path, source_rc=None):
    source = (source_rc or RC).read_text()
    at = source.rfind('>')
    assert at > 0 and not source[at + 1:].strip()
    path.write_text(source[:at] + '\n' + (HERE / 'bridge.lua').read_text()
                    + '\n' + (HERE / 'direct_transport.lua').read_text()
                    + '\n>\ndump_order += tactical_dump\n')


class Environment:
    """One engine process and a new private filesystem for each reset.

    step is one controller decision, not necessarily one game turn: baseline
    and Tab are macro-actions. Invalid/no-turn actions remain in the dataset.
    """
    def __init__(self, workspace, source_rc=None):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.child = None
        self.source_rc = source_rc

    def launch(self, checkpoint=None):
        self.close()
        self.work = Path(tempfile.mkdtemp(prefix='worker-', dir=self.workspace))
        for directory in ('saves', 'morgue', 'macros'):
            (self.work / directory).mkdir()
        rc = self.work / 'trial.rc'
        if checkpoint:
            case = Path(checkpoint).resolve()
            metadata = json.loads((case / 'case.json').read_text())
            if metadata['engine_sha256'] != sha(ENGINE):
                raise ValueError('Checkpoint engine mismatch')
            if metadata['save_sha256'] != sha(case / 'checkpoint.cs'):
                raise ValueError('Checkpoint checksum mismatch')
            if metadata['rc_sha256'] != sha(case / 'trial.rc'):
                raise ValueError('Checkpoint RC checksum mismatch')
            shutil.copy2(case / 'checkpoint.cs', self.work / 'saves' / (NAME+'.cs'))
            shutil.copy2(case / 'trial.rc', rc)
        else:
            make_rc(rc,self.source_rc)
        args = ['-name', NAME, '-rc', str(rc), '-seed', SEED,
                '-no-player-bones', '-extra-opt-last', 'species=Minotaur',
                '-extra-opt-last', 'background=Berserker',
                '-extra-opt-last', 'weapon=hand axe']
        for option, folder in [('save_dir','saves'), ('morgue_dir','morgue'),
                               ('macro_dir','macros')]:
            args += ['-extra-opt-last', f'{option}={self.work / folder}/']
        self.direct_transport = 'TB_DIRECT_TRANSPORT=true' in rc.read_text()
        self.transcript = (self.work / 'terminal.txt').open('w')
        (self.work/'run.json').write_text(json.dumps({
            'schema_version':1,'case':str(checkpoint) if checkpoint else None,
            'engine_sha256':sha(ENGINE),'rc_sha256':sha(rc),
            'adapter_sha256':sha(Path(__file__)),'seed':SEED,'character':NAME,
            'transport':'ready_getch' if self.direct_transport else 'legacy_console',
            'checkpoint_sha256':sha(Path(checkpoint)/'checkpoint.cs') if checkpoint else None,
            'started_unix':time.time()},indent=2)+'\n')
        self.child = pexpect.spawn(str(ENGINE), args, cwd=str(ENGINE.parent),
            env={**os.environ, 'TERM':'xterm'}, encoding='utf-8', codec_errors='replace',
            dimensions=(50,160), timeout=30)
        self.child.logfile_read = self.transcript
        self.state=self.await_state(startup=True)
        return self.state

    def await_state(self, startup=False, expected_seq=None):
        deadline = time.monotonic() + (180 if startup else 20)
        probed = False
        while time.monotonic() < deadline:
            if getattr(self,'direct_transport',False):
                # getch inside ready need not flush the terminal message window.
                # The completed structured dump is the authoritative boundary.
                try:
                    match=re.search(r'^TBJSON (.+)$',
                        (self.work/'morgue'/(NAME+'.txt')).read_text(),re.M)
                    state=json.loads(match[1]) if match else None
                    if state and (expected_seq is None or state['seq']==expected_seq):
                        self.state=state
                        return state
                except (OSError,ValueError):pass
            i = self.child.expect([r'TBREADY (\d+) END', r'You die\.\.\.',
                r'Hit .* to (?:continue|start)', r'Press .* to (?:continue|start)',
                pexpect.EOF, pexpect.TIMEOUT], timeout=0.05 if getattr(self,'direct_transport',False) else 2)
            if i == 0:
                seq = int(self.child.match.group(1))
                if expected_seq is not None and seq < expected_seq:
                    continue  # ncurses redraws old messages, not new events.
                dump = self.work / 'morgue' / (NAME+'.txt')
                match = re.search(r'^TBJSON (.+)$', dump.read_text(), re.M)
                if not match:
                    raise RuntimeError('Missing structured observation in dump')
                state = json.loads(match.group(1))
                if state['seq'] != seq:
                    raise RuntimeError('Stale observation')
                self.state = state
                return state
            if i == 1:
                return {'terminal': 'death'}
            if i in (2,3) and startup:
                self.child.send(' ')
            elif i == 4:
                raise RuntimeError(f'Unexpected engine exit; see {self.work}')
            elif i == 5 and not startup and not probed and not getattr(self,'direct_transport',False):
                # No-op commands need not trigger another ready(). Confirm the
                # interpreter before asking for a read-only boundary snapshot.
                probed = True
                self.child.send('\x04')
                self.child.expect_exact('[Hit ESC to exit interpreter.]', timeout=3)
                self.child.send('assert(not TB.pending); crawl.dump_char(); '
                    'crawl.mpr("TB".."READY "..TB.seq.." END")\r')
                # Snapshot is emitted in the interpreter; leave it before next step.
                self.child.expect(r'TBREADY (\d+) END', timeout=3)
                self.child.send('\x1b')
                dump = (self.work/'morgue'/(NAME+'.txt')).read_text()
                state = json.loads(re.search(r'^TBJSON (.+)$',dump,re.M)[1])
                if state['seq'] != expected_seq:
                    raise RuntimeError('No-op probe did not reach requested action')
                self.state = state
                return state
        raise TimeoutError(f'No decision boundary (not counted as death); see {self.work}')

    def console(self, code):
        if getattr(self,'direct_transport',False):
            self.child.send('\x1b')
        self.child.send('\x04')
        # Never type Lua into a game/menu: require explicit interpreter handshake.
        self.child.expect_exact('[Hit ESC to exit interpreter.]', timeout=5)
        ack = 'ACK'+str(self.state['seq']+1)+' END'
        self.child.send(code+'; crawl.mpr("TB"..'+json.dumps(ack)+')\r')
        self.child.expect_exact('TB'+ack, timeout=5)
        self.child.send('\x1b')

    def step(self, action):
        if action not in ACTIONS:
            raise ValueError(action)
        before = self.state
        if before.get('terminal'):
            raise RuntimeError('Episode is terminal; reset before stepping')
        try:
            if self.direct_transport:
                self.child.send(chr(97+list(ACTIONS).index(action)))
            else:
                self.console('tb_request('+json.dumps(ACTIONS[action])+')')
            after = self.await_state(expected_seq=before['seq']+1)
        except Exception as exc:
            with (self.work/'errors.jsonl').open('a') as f:
                f.write(json.dumps({'observation':before,'action':action,
                                    'error':str(exc),'truncated':True})+'\n')
            raise
        self.state=after
        row = {'observation': before, 'action': action, 'next_observation': after,
               'terminated': after.get('terminal') == 'death',
               'turn_delta': after.get('turn',before['turn'])-before['turn']}
        with (self.work / 'transitions.jsonl').open('a') as f:
            f.write(json.dumps(row, sort_keys=True)+'\n')
        return after

    def reset(self, case_id):
        return self.launch(case_id)

    def capture(self, destination, warmup=0):
        destination = Path(destination).resolve()
        if destination.exists():
            raise FileExistsError(destination)
        observation = self.launch()
        if observation.get('terminal'):
            raise RuntimeError('Died before first-contact checkpoint')
        for _ in range(warmup):
            observation = self.step('baseline')
            if observation.get('terminal'):
                raise RuntimeError('Died before requested checkpoint')
        self.console('tb_request("CMD_SAVE_GAME_NOW")')
        self.child.expect([pexpect.EOF, 'view rc file information and log'], timeout=20)
        self.close()
        save = self.work / 'saves' / (NAME+'.cs')
        if not save.exists():
            raise RuntimeError('Save missing')
        destination.mkdir(parents=True)
        shutil.copy2(save, destination / 'checkpoint.cs')
        shutil.copy2(self.work / 'trial.rc', destination / 'trial.rc')
        metadata = {'id':destination.name,'seed':SEED,'character':NAME,
                    'engine_sha256':sha(ENGINE),'source_rc_sha256':sha(RC),
                    'rc_sha256':sha(destination/'trial.rc'),
                    'save_sha256':sha(destination/'checkpoint.cs'),
                    'observation':observation,'capture_worker':str(self.work),
                    'warmup_decisions':warmup,
                    'fidelity':'save/load may diverge from uninterrupted trajectory'}
        (destination / 'case.json').write_text(json.dumps(metadata,indent=2)+'\n')
        return metadata

    def close(self):
        if self.child is not None:
            self.child.close(force=True)
            self.child = None
            self.transcript.close()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['capture','rollout'])
    p.add_argument('case',type=Path)
    p.add_argument('--workspace',type=Path,default=HERE/'artifacts')
    p.add_argument('--steps',type=int,default=200)
    p.add_argument('--action',choices=ACTIONS,default='baseline')
    p.add_argument('--warmup',type=int,default=0)
    args=p.parse_args()
    env=Environment(args.workspace)
    try:
        if args.command=='capture':
            state=env.capture(args.case,args.warmup)['observation']
        else:
            state=env.reset(args.case)
            for _ in range(args.steps):
                state=env.step(args.action)
                if state.get('terminal'): break
        print(json.dumps({'work':str(env.work),'result':{k:v for k,v in state.items()
              if k not in ('cells','inventory','messages')}}))
    finally:
        env.close()


if __name__=='__main__':
    main()
