"""Run-scoped disk backpressure and completed-artifact retention.

Never prune snapshots, checkpoints, metrics, failures, or incomplete episodes.
"""
import gzip
import json
import os
from pathlib import Path
import shutil
import threading
import time

GIB = 1024 ** 3
_root = None
_lock = threading.RLock()
_paused = threading.Event()


def configure(root):
    global _root
    _root = Path(root).resolve()
    _paused.clear()
    (_root / "storage_pauses").mkdir(exist_ok=True)


def limits():
    return {"pause_free_bytes": 20 * GIB, "resume_free_bytes": 22 * GIB,
            "replay_max_bytes": 2 * GIB, "replay_max_rows": 20000}


def guard():
    """Block at a decision/write boundary; Crawl waits for input meanwhile."""
    if _root is None:
        return
    marker = _root / "storage_pauses" / f"{os.getpid()}-{threading.get_ident()}.json"
    if shutil.disk_usage(_root).free >= limits()["pause_free_bytes"] and not _paused.is_set():
        return
    _paused.set()
    marker.write_text(json.dumps({"phase": "paused_low_disk", "pid": os.getpid(),
        "free_bytes": shutil.disk_usage(_root).free, "since": time.time(), **limits()}))
    try:
        while shutil.disk_usage(_root).free < limits()["resume_free_bytes"]:
            time.sleep(5)
        _paused.clear()
    finally:
        marker.unlink(missing_ok=True)


def open_text(path):
    path = Path(path)
    return gzip.open(path, "rt") if path.suffix == ".gz" else path.open()


def replay_files(directory):
    return sorted([*Path(directory).glob("*.jsonl"), *Path(directory).glob("*.jsonl.gz")])


def result_path(path):
    path = Path(path)
    if path.suffix == ".gz":
        path = path.with_suffix("")
    return path.with_suffix(".result.json")


def compress(path):
    path = Path(path)
    if not path.exists() or path.is_symlink():
        return
    guard()
    target = path.with_name(path.name + ".gz")
    tmp = target.with_name(target.name + ".tmp")
    source_stat = path.stat()
    with path.open("rb") as source, gzip.open(tmp, "wb", compresslevel=1) as dest:
        while chunk := source.read(1024 * 1024):
            guard()
            dest.write(chunk)
    os.utime(tmp, (source_stat.st_atime, source_stat.st_mtime))
    tmp.replace(target)
    path.unlink()


def finish_logs(works, redundant=False):
    """Only called after successful execution and durable replay/result writes."""
    for work in works:
        work = Path(work)
        if work.is_symlink() or not (work / "run.json").is_file():
            continue
        events = work / "events.jsonl"
        if redundant and events.is_file() and not events.is_symlink():
            events.unlink()
        else:
            compress(events)
        compress(work / "terminal.txt")


def maintain(root, max_bytes=None, max_rows=None):
    """Prune oldest whole completed replay shards, with a durable audit trail."""
    root = Path(root)
    with _lock:
        completed = [p for p in replay_files(root / "replay")
                     if not p.is_symlink() and result_path(p).is_file()]
        for p in completed:
            if p.suffix != ".gz":
                compress(p)
            result = json.loads(result_path(p).read_text())
            works = result.get("work_paths", [result.get("work")])
            safe = [Path(w) for w in works if w and Path(w).name.startswith("general-")
                    and Path(w).resolve().is_relative_to((root / "actors").resolve())]
            finish_logs(safe, redundant=True)
        completed = sorted([p for p in replay_files(root / "replay")
                            if not p.is_symlink() and result_path(p).is_file()],
                           key=lambda p: p.stat().st_mtime)
        sizes = {p: p.stat().st_size for p in completed}
        rows = {p: int(json.loads(result_path(p).read_text())["steps"]) for p in completed}
        total, count = sum(sizes.values()), sum(rows.values())
        max_bytes = limits()["replay_max_bytes"] if max_bytes is None else max_bytes
        max_rows = limits()["replay_max_rows"] if max_rows is None else max_rows
        removed = []
        for p in completed:
            if total <= max_bytes and count <= max_rows:
                break
            event = {"time": time.time(), "removed_replay": str(p),
                     "bytes": sizes[p], "rows": rows[p], "reason": "replay_retention"}
            (root / "metrics").mkdir(exist_ok=True)
            with (root / "metrics" / "storage.jsonl").open("a") as log:
                log.write(json.dumps(event) + "\n")
            p.unlink()
            total -= sizes[p]
            count -= rows[p]
            removed.append(event)
        return {"retained_replay_bytes": total, "retained_replay_rows": count,
                "removed": removed}


def health(root):
    root = Path(root)
    pauses = []
    for path in (root / "storage_pauses").glob("*.json"):
        try:
            record = json.loads(path.read_text())
            os.kill(record["pid"], 0)
            pauses.append(record)
        except (ProcessLookupError, FileNotFoundError, json.JSONDecodeError):
            continue
    return {"free_bytes": shutil.disk_usage(root).free,
            "paused": bool(pauses), "workers": pauses, **limits()}
