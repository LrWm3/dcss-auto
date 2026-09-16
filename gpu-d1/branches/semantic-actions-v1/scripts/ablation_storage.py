"""Bounded atomic writes for an owned ablation output directory."""
import json
import os
import pathlib
import shutil


class DiskBudgetError(RuntimeError):
    pass


class LimitedWriter:
    def __init__(self, stream, limit):
        self.stream, self.limit = stream, limit

    def write(self, data):
        if self.stream.tell() + len(data) > self.limit:
            raise DiskBudgetError(f'File would exceed its {self.limit} byte reservation')
        return self.stream.write(data)

    def __getattr__(self, key):
        return getattr(self.stream, key)


class Store:
    def __init__(self, root, max_bytes, reserve_bytes):
        self.root = pathlib.Path(root).resolve()
        self.max_bytes, self.reserve_bytes = max_bytes, reserve_bytes

    def used(self):
        # Never follow directory symlinks into a corpus or an unrelated run.
        total = 0
        for base, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = [d for d in dirs if not (pathlib.Path(base) / d).is_symlink()]
            total += sum((pathlib.Path(base) / f).lstat().st_size for f in files)
        return total

    def ensure(self, extra):
        used = self.used()
        free = shutil.disk_usage(self.root).free
        if used + extra > self.max_bytes:
            raise DiskBudgetError(f'Suite disk cap: {used:,} used + {extra:,} reserved > {self.max_bytes:,}')
        if free - extra < self.reserve_bytes:
            raise DiskBudgetError(f'Free-space reserve: {free:,} free - {extra:,} needed < {self.reserve_bytes:,}')

    def target(self, relative):
        path = self.root / relative
        # Refuse symlink destinations/parents so recovery cannot delete outside
        # this suite. Output files themselves are never symlinks.
        if not path.resolve().is_relative_to(self.root):
            raise ValueError('Output escapes suite directory')
        for p in (path, *path.parents):
            if p == self.root:
                break
            if p.is_symlink():
                raise ValueError(f'Symlink output is not permitted: {p}')
        return path

    def atomic(self, relative, writer, max_size):
        path = self.target(relative)
        tmp = path.with_name(path.name + '.tmp')
        # This specific name is owned by the atomic writer. Never glob-delete
        # checkpoints, earlier runs, fixtures, or user files.
        self.target(tmp.relative_to(self.root))
        if tmp.exists():
            tmp.unlink()
        self.ensure(max_size)  # includes old destination and temporary coexistence
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with tmp.open('xb') as raw:
                writer(LimitedWriter(raw, max_size))
                raw.flush()
                os.fsync(raw.fileno())
            os.replace(tmp, path)
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if tmp.exists():
                tmp.unlink()

    def json(self, relative, value):
        data = (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()
        if len(data) > 16 * 1024**2:
            raise DiskBudgetError('JSON report exceeds 16 MiB; refusing unbounded history')
        self.atomic(relative, lambda f: f.write(data), len(data))
