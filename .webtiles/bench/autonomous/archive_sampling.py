"""Deterministic, stratified archive coverage instead of newest death states."""
import json
import random


def select_cases(paths, cycle, limit=4):
    rng = random.Random(cycle)
    buckets = {'encounter_start': [], 'healthy': [], 'danger': [], 'coverage': []}
    for path in sorted(paths):
        try:
            tags = json.loads((path.parent / 'sampling.json').read_text())
        except (OSError, ValueError):
            tags = {}
        buckets.get(tags.get('category'), buckets['coverage']).append(path.parent)
    for bucket in buckets.values():
        rng.shuffle(bucket)
    selected = []
    while len(selected) < limit and any(buckets.values()):
        for bucket in buckets.values():
            if bucket and len(selected) < limit:
                selected.append(bucket.pop())
    return selected
