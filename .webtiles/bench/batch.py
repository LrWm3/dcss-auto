"""Config-driven tmux trials. Standard library only; never sends gameplay input."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import re
import shlex
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import runner

ROOT = Path(__file__).resolve().parents[2]
BENCH = Path(__file__).resolve().parent
STATE = BENCH / 'batches'


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configured_rc(source, overrides):
    """Apply explicit policy knobs to the snapshot, leaving the source RC alone."""
    text = source.decode()
    policy = re.search(r'AUTOCrawl_TACTICS = \{(.*?)\n\}', text, re.S)
    if not policy:
        raise ValueError('RC has no tactical policy table')
    block = policy.group(1)
    for key, value in overrides.items():
        pattern = r'\b' + re.escape(key) + r'\s*=\s*(true|false|[0-9.]+)'
        match = re.search(pattern, block)
        if not match or type(value) not in (bool, int, float):
            raise ValueError(f'Invalid tactical override: {key}')
        is_bool = match.group(1) in ('true', 'false')
        if is_bool != isinstance(value, bool) or (not is_bool and not 0 <= value <= 100):
            raise ValueError(f'Invalid tactical value: {key}')
        literal = str(value).lower()
        block = re.sub(pattern, lambda m: key + ' = ' + literal, block)
    return (text[:policy.start(1)] + block + text[policy.end(1):]).encode()


def config(path):
    cfg = json.loads(Path(path).read_text())
    if not re.fullmatch(r'[A-Za-z0-9_-]+', cfg['version']):
        raise ValueError('Invalid version')
    sessions, names, seeds = set(), set(), set()
    for row in cfg['sessions']:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', row['session']):
            raise ValueError('Invalid session name')
        if not re.fullmatch(r'[A-Za-z0-9]{1,20}', row['character']):
            raise ValueError('Character must be 1–20 ASCII letters/digits')
        if not isinstance(row['seed'], str) or row['seed'] not in runner.SEEDS:
            raise ValueError('Use a fixed benchmark seed encoded as a string')
        for value, seen in ((row['session'], sessions), (row['character'], names),
                            (row['seed'], seeds)):
            if value in seen:
                raise ValueError('Duplicate session, character or seed')
            seen.add(value)
    if not sessions:
        raise ValueError('Empty batch')
    for key in ('poll_seconds', 'stale_seconds'):
        if key in cfg and (not isinstance(cfg[key], (int, float)) or cfg[key] <= 0):
            raise ValueError(f'{key} must be positive')
    return cfg


def panes(session):
    result = subprocess.run(['tmux', 'list-panes', '-s', '-t', '=' + session,
                             '-F', '#{pane_id}'], capture_output=True, text=True)
    return result.stdout.split() if result.returncode == 0 else []


def reusable(session, ids):
    # Only reuse our own single-pane sessions, after a verified terminal morgue.
    if len(ids) != 1:
        return False
    for manifest in STATE.glob('*/manifest.json'):
        for row in json.loads(manifest.read_text())['sessions']:
            if (row['session'] == session and row.get('pane') == ids[0]
                    and row.get('status') == 'death'):
                screen = command('tmux', 'capture-pane', '-p', '-t', ids[0], '-S', '-200')
                pid = command('tmux', 'display-message', '-p', '-t', ids[0], '#{pane_pid}')
                try:
                    argv = Path('/proc', pid, 'cmdline').read_bytes().decode().split('\0')
                except (OSError, UnicodeError):
                    continue
                same_game = any(argv[i:i+2] == ['-name', row['character']]
                                for i in range(len(argv)))
                game = ROOT / 'crawl-0.35/crawl-ref/source'
                dump = Path(row.get('dump', ''))
                verified = dump.is_file() and terminal_dump(dump, row)
                no_save = not list((game / 'saves').glob(row['character'] + '.*'))
                death_screen = (row['character'] in screen and 'You die...' in screen)
                inventory_screen = 'Gear:' in screen and 'gear slots' in screen
                menu_screen = ('Enter your name: '+row['character'] in screen
                               and 'Choices:' in screen and 'Dungeon Crawl' in screen)
                if same_game and verified and no_save and (death_screen or inventory_screen or menu_screen):
                    return True
    return False


def start(cfg, dry_run):
    directory = STATE / cfg['version']
    if directory.exists():
        raise ValueError('Batch exists; use status/watch to resume collecting it')
    log = BENCH / 'runs.jsonl'
    if log.exists() and any(json.loads(line)['version'] == cfg['version']
                            for line in log.read_text().splitlines()):
        raise ValueError('Version already has benchmark results; choose a new version')
    source = ROOT / cfg.get('rc', '.webtiles/rcs/codex-autocrawl.rc')
    engine = ROOT / 'crawl-0.35/crawl-ref/source/crawl-webtiles'
    game = engine.parent
    old = {}
    # Preflight the entire batch before starting anything.
    for row in cfg['sessions']:
        name = row['character']
        if (list((game / 'saves').glob(name + '.*'))
                or list((game / 'morgue').glob('morgue-' + name + '-*.txt'))
                or (ROOT / '.webtiles/sockets' / (name + ':terminal.sock')).exists()):
            raise ValueError(f'{name}: already used; choose a fresh character name')
        ids = panes(row['session'])
        if ids and not reusable(row['session'], ids):
            raise ValueError(f"{row['session']}: not a verified dead runner-owned session")
        old[row['session']] = ids
    rc_bytes = configured_rc(source.read_bytes(), cfg.get('tactics', {}))
    cfg.update(rc_sha256=hashlib.sha256(rc_bytes).hexdigest(), engine_sha256=sha(engine),
               commit=command('git', '-C', str(ROOT), 'rev-parse', 'HEAD'),
               rc_dirty=bool(command('git', '-C', str(ROOT), 'status', '--porcelain', '--', str(source))),
               started_at=time.time())
    snapshot = directory / 'tested.rc'
    if dry_run:
        print(json.dumps(cfg, indent=2))
        return
    directory.mkdir(parents=True)
    snapshot.write_bytes(rc_bytes)
    for row in cfg['sessions']:
        row['status'] = 'not_started'
    save(directory / 'manifest.json', cfg)
    for row in cfg['sessions']:
        argv = [str(ROOT / 'play-webtiles.sh'), row['character'], '-rc', str(snapshot),
                '-seed', row['seed'], '-extra-opt-last', 'species=Minotaur',
                '-extra-opt-last', 'background=Berserker', '-extra-opt-last', 'weapon=hand axe']
        ids = old[row['session']]
        if ids:
            command('tmux', 'respawn-pane', '-k', '-t', ids[0], shlex.join(argv))
            row['pane'] = ids[0]
        else:
            row['pane'] = command('tmux', 'new-session', '-d', '-P', '-F', '#{pane_id}',
                                  '-s', row['session'], shlex.join(argv))
        row.update(status='running', last_change=time.time())
        save(directory / 'manifest.json', cfg)
    print(f"Started {len(cfg['sessions'])} games; snapshot: {snapshot}")


def terminal_dump(path, row):
    text = path.read_text()
    return (f"Game seed: {row['seed']} " in text
            and re.search(r'^' + re.escape(row['character']) + r' .*Turns:', text, re.M)
            and 'You die...' in text)


def collect(version):
    directory = STATE / version
    cfg = json.loads((directory / 'manifest.json').read_text())
    game = ROOT / 'crawl-0.35/crawl-ref/source'
    rows = [json.loads(line) for line in (BENCH / 'runs.jsonl').read_text().splitlines()]
    for row in cfg['sessions']:
        recorded = next((r for r in rows if r['version']==version and r['seed']==row['seed']), None)
        if recorded and recorded['outcome'] in ('paused', 'complete'):
            row['status']=recorded['outcome']
            continue
        if row['status'] == 'death':
            continue
        dumps = sorted((game / 'morgue').glob(f"morgue-{row['character']}-*.txt"))
        dumps = [p for p in dumps if p.stat().st_mtime >= cfg['started_at'] and terminal_dump(p, row)]
        if dumps:
            existing = next((r for r in rows if r['version'] == version and r['seed'] == row['seed']), None)
            if existing:
                if existing['character'] != row['character'] or existing['evidence_sha256'] != sha(dumps[-1]):
                    raise ValueError('Conflicting existing benchmark evidence')
            else:
                runner.record(SimpleNamespace(version=version, character=row['character'],
                    outcome='death', commit=cfg['commit'], rc_sha=cfg['rc_sha256'],
                    engine_sha=cfg['engine_sha256'], dump=str(dumps[-1])))
            row.update(status='death', dump=str(dumps[-1]))
            continue
        if not row.get('pane') or panes(row['session']) != [row['pane']]:
            row['status'] = 'missing_session'
            continue
        screen = command('tmux', 'capture-pane', '-p', '-t', row['pane'], '-S', '-200')
        (directory / (row['character'] + '.screen.txt')).write_text(screen + '\n')
        digest = hashlib.sha256(screen.encode()).hexdigest()
        if digest != row.get('screen_sha256'):
            row.update(screen_sha256=digest, last_change=time.time())
        if 'ROUTE COMPLETE: Zot route explored' in screen or 'SUCCESS: D:15 exploration complete' in screen:
            row['status'] = 'completion_reported'
        elif time.time() - row['last_change'] >= cfg.get('stale_seconds', 120):
            row['status'] = 'suspected_stall'
        else:
            row['status'] = 'running'
    save(directory / 'manifest.json', cfg)
    print(json.dumps({r['character']: r['status'] for r in cfg['sessions']}))
    return cfg


@contextlib.contextmanager
def locked():
    STATE.mkdir(exist_ok=True)
    with (STATE / '.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('start')
    p.add_argument('config')
    p.add_argument('--dry-run', action='store_true')
    for action in ('status', 'watch'):
        p = sub.add_parser(action)
        p.add_argument('version')
        if action == 'watch':
            p.add_argument('--timeout', type=float, default=1800)
    args = parser.parse_args()
    if args.action == 'start':
        with locked():
            start(config(args.config), args.dry_run)
        return
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.version):
        parser.error('Invalid version')
    deadline = time.monotonic() + getattr(args, 'timeout', 0)
    while True:
        with locked():
            cfg = collect(args.version)
        if args.action == 'status' or all(r['status'] != 'running' for r in cfg['sessions']):
            return
        if time.monotonic() >= deadline:
            print('Watch timeout; games left untouched. Run watch again to resume.')
            return
        time.sleep(min(30, max(1, cfg.get('poll_seconds', 10))))


if __name__ == '__main__':
    main()
