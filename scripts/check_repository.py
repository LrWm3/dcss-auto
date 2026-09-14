#!/usr/bin/env python3
"""Check the Git index for accidental large/generated files before pushing."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE = 5 * 1024 * 1024


def main():
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).split(b'\0')
    bad = []
    total = 0
    count = 0
    for raw in names:
        if not raw:
            continue
        name = raw.decode()
        size = int(subprocess.check_output(['git', 'cat-file', '-s', ':' + name], cwd=ROOT))
        total += size
        count += 1
        parts = Path(name).parts
        if size > MAX_FILE:
            bad.append(f'{name}: {size} bytes exceeds 5 MiB')
        if ('artifacts' in parts or 'crawl-0.35' in parts or '__pycache__' in parts
                or any(p in ('.venv', '.build-venv', '.rl-venv') for p in parts)
                or Path(name).suffix in ('.pt', '.pth', '.pem', '.key', '.cs')
                or Path(name).name == '.env'):
            bad.append(f'{name}: generated/private path')
    print(f'Index: {count} files, {total / 1024**2:.2f} MiB; largest allowed file: 5 MiB')
    for problem in bad:
        print('ERROR:', problem)
    return bool(bad)


if __name__ == '__main__':
    raise SystemExit(main())
