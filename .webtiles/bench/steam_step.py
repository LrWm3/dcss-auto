"""One authorized diagnostic decision, followed by a read-only state dump."""
import subprocess
import sys
import time
import re
import argparse
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--session',default='codex-bench4')
parser.add_argument('--character',default='CodexSteamDebug1')
parser.add_argument('--step',action='store_true')
parser.add_argument('--run',type=int)
args=parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9]{1,20}',args.character):
    raise SystemExit('Invalid character name')
SESSION = args.session
DUMP = Path('crawl-0.35/crawl-ref/source/morgue') / (args.character+'.txt')

def console(code):
    subprocess.run(['tmux', 'send-keys', '-t', SESSION, 'C-d'], check=True)
    subprocess.run(['tmux', 'send-keys', '-t', SESSION, '-l', code], check=True)
    subprocess.run(['tmux', 'send-keys', '-t', SESSION, 'Enter'], check=True)
    time.sleep(.15)
    subprocess.run(['tmux', 'send-keys', '-t', SESSION, 'Escape'], check=True)
    time.sleep(.15)

previous = DUMP.read_text() if DUMP.exists() else ''
old_notes = previous.split('Notes\n', 1)[-1].split('Illustrated notes', 1)[0].rstrip()
deaths = sorted(DUMP.parent.glob('morgue-'+args.character+'-*.txt'))
if deaths and (args.step or args.run):
    raise SystemExit('Character is dead; refusing gameplay input.')
pid = subprocess.check_output(['tmux', 'display-message', '-p', '-t', SESSION,
                               '#{pane_pid}'], text=True).strip()
argv = Path('/proc', pid, 'cmdline').read_bytes().decode().split('\0')
if not any(argv[i:i+2] == ['-name', args.character] for i in range(len(argv))):
    raise SystemExit('Session no longer belongs to the diagnostic character.')
if args.run:
    console('autocrawl_steam_run('+str(args.run)+')')
    time.sleep(1)
elif args.step:
    console('autocrawl_steam_step()')
deaths = sorted(DUMP.parent.glob('morgue-'+args.character+'-*.txt'))
if not deaths:
    console('autocrawl_steam_report(); crawl.dump_char()')
text = (deaths[-1] if deaths else DUMP).read_text()
notes = text.split('Notes\n', 1)[1].split('Illustrated notes', 1)[0]
delta = notes[len(old_notes):] if notes.startswith(old_notes) else notes[-6500:]
for block in re.split(r'(?=^\s*\d+ \|)', delta, flags=re.M):
    if any(s in block for s in ('TRACE tile', '<cyan>', 'exit interpreter.', 'autocrawl_steam_')):
        continue
    print(block.rstrip())
