"""One evidence-preserving retry for a specific pre-observation engine failure.

Never retry deaths, gameplay stalls, timeouts or arbitrary engine exits. This is
not best-of-N outcome selection: no gameplay observation/action may have occurred.
"""
from pathlib import Path


def retryable(row):
    if (row.get('outcome')!='harness_error' or row.get('decisions')!=0 or
        row.get('startup_attempts') or 'features' in row or 'available' in row):
        return False
    terminal=Path(row['worker'])/'terminal.txt'
    if not terminal.exists(): return False
    text=terminal.read_text(errors='replace')
    return ("Map 'regret_index_lairdec_grave_grove' has no (possible) exits" in text
            and 'lair.des:' in text and 'TBREADY' not in text and 'TBJSON' not in text)


def run_with_retry(attempt, previous=None):
    """attempt(index) returns a raw run result; keep the first attempt untouched."""
    row=attempt(0) if previous is None else previous
    if not retryable(row): return row
    new=dict(attempt(1))
    for key in ('phase','split','family_id','split_group','recipe','policy'):
        if key in row:new[key]=row[key]
    new['startup_attempts']=[row]
    new['retry_reason']='known pre-observation Lair map-parser failure'
    return new
