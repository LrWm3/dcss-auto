#!/usr/bin/env python3
"""Rebuild the historical evidence index, not the manually adjudicated ledger.

Read-only against experiments, Git, and explicitly scoped Codex conversation
messages. Writes ONLY generated inventory files in this script's directory.
Never exports reasoning, tool payloads, credentials, or unrelated conversations.
"""
import argparse
import collections
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BENCH = REPO / '.webtiles/bench'
CURRENT_THREAD = '01a08678-6099-7be1-a4ea-ad3739409bda'


def relative(path):
    try: return str(path.relative_to(REPO))
    except ValueError: return str(path)


def link(path, label=None, line=None):
    path=Path(path)
    target=str(path.resolve())+(f':{line}' if line else '')
    return f'[{label or path.name}](<{target}>)'


def clean(value, limit=360):
    return re.sub(r'\s+', ' ', str(value)).replace('|','/').replace('[','(').replace(']',')')[:limit].rstrip()


def session_inventory(codex, cutoff):
    found={}; excluded=[]
    for root in (codex/'sessions',codex/'archived_sessions'):
        if not root.exists(): continue
        for path in sorted(root.rglob('*.jsonl')):
            try:
                with path.open() as stream: meta=json.loads(next(stream)).get('payload',{})
            except (OSError,ValueError,StopIteration): continue
            if meta.get('cwd')!=str(REPO): continue
            sid=meta.get('id',meta.get('session_id'))
            if isinstance(meta.get('source'),dict): continue  # audit subagents aren't old evidence
            found[sid]=(path,meta)
    lineage=[]; sid=CURRENT_THREAD; bound=None
    while sid in found:
        path,meta=found[sid]
        lineage.append((sid,path,meta,bound))
        sid=meta.get('forked_from_id'); bound=meta.get('forked_from_ordinal_exclusive')
    if not lineage: raise ValueError('explicit current thread not found')
    included={x[0] for x in lineage}
    for sid,(path,meta) in found.items():
        if sid not in included:
            excluded.append({'id':sid,'path':str(path),'reason':'different conversation lineage (manual gameplay/context), not training evidence'})
    sessions=[]; events=[]
    for sid,path,meta,bound in reversed(lineage):
        users=[]; answers=[]; question=None; digest=hashlib.sha256(); last_line=0
        with path.open('rb') as stream:
            for number,raw in enumerate(stream,1):
                record=json.loads(raw)
                if bound is not None and record.get('ordinal',-1)>=bound: break
                if record.get('timestamp','')>=cutoff: break
                digest.update(raw); last_line=number
                p=record.get('payload',{})
                if record.get('type')!='response_item' or p.get('type')!='message':continue
                text='\n'.join(c.get('text','') for c in p.get('content',[]) if isinstance(c,dict))
                if p.get('role')=='user':
                    if text.startswith(('<recommended_plugins>','<environment_context>','<turn_aborted>')):continue
                    question={'line':number,'text':clean(text,220),'timestamp':record['timestamp']}
                    users.append(question)
                elif p.get('role')=='assistant' and p.get('phase') in ('final','final_answer'):
                    item={'thread':sid,'path':str(path),'line':number,'ordinal':record.get('ordinal'),
                          'timestamp':record['timestamp'],'request':question,'conclusion_excerpt':clean(text,650),
                          'evidence_grade':'session report, not independent verification'}
                    events.append(item); answers.append(number)
        sessions.append({'id':sid,'path':str(path),'parent':meta.get('forked_from_id'),
                         'ordinal_exclusive':bound,'last_included_line':last_line,
                         'included_prefix_sha256':digest.hexdigest(),'user_messages':len(users),
                         'final_answers':len(answers),'started_at':meta.get('timestamp')})
    return {'lineage':sessions,'excluded_related_sessions':excluded,'events':events}


def documents():
    paths=[]
    for root in (BENCH,BENCH/'autonomous',BENCH/'tactical',BENCH/'archive',BENCH/'evidence', REPO/'.webtiles/tests'):
        paths.extend(p for p in sorted(root.glob('*.md')) if p.name != 'EXPERIMENT-LEDGER.md')
    paths.extend(REPO/p for p in ('.webtiles/ARCHITECTURE.md', '.webtiles/ROUTE.md') if (REPO/p).exists())
    paths.extend(REPO/p for p in ('CODEX-MIBE-RUN.md','WEBTILES.md','BEGINNER-AGENT-PLAN.md',
                                  'DCSS-MECHANICS.md','S-BRANCH-THREATS.md','VAULTS-THREATS.md') if (REPO/p).exists())
    result=[]
    for path in paths:
        raw=path.read_bytes(); sections=[]
        for number,text in enumerate(raw.decode(errors='replace').splitlines(),1):
            if re.match(r'^#{1,4} ',text):sections.append({'line':number,'heading':text.lstrip('# ')})
        result.append({'path':relative(path),'sha256':hashlib.sha256(raw).hexdigest(),'sections':sections})
    return result


def commits():
    raw=subprocess.check_output(['git','log','--reverse','--date=iso-strict','--format=%H%x09%ad%x09%s'],cwd=REPO,text=True)
    return [dict(zip(('sha','date','subject'),line.split('\t',2))) for line in raw.splitlines()]


def compact_evidence():
    rows=[]
    for root in (BENCH/'evidence', BENCH/'tactical/evidence'):
        if not root.exists(): continue
        for path in sorted(root.iterdir()):
            if not path.is_file(): continue
            raw=path.read_bytes()
            rows.append({'path':relative(path),'bytes':len(raw),
                         'sha256':hashlib.sha256(raw).hexdigest()})
    return rows


def artifacts():
    rows=[]
    for base in (BENCH/'autonomous/artifacts',BENCH/'tactical/artifacts',BENCH/'batches'):
        if not base.exists():continue
        for root in sorted(base.iterdir()):
            if not root.is_dir():continue
            manifests=[]; reported={}
            # Deliberately shallow. Never walk worker saves/replay/engine caches.
            for p in sorted(root.glob('*.json')):
                manifests.append(relative(p))
                if p.name in ('latest_status.json','status.json','summary.json','comparison.json','gate.json','report.json') and p.stat().st_size<2_000_000:
                    try:
                        value=json.loads(p.read_text())
                        if isinstance(value,dict):
                            reported[p.name]={k:v for k,v in value.items() if isinstance(v,(str,int,float,bool,type(None))) and len(str(v))<240}
                    except (ValueError,OSError): pass
            kind='support/cache/worker' if root.name.startswith(('worker-','engine','engines')) else 'run directory (not proof of completion)'
            rows.append({'path':relative(root),'kind':kind,'root_json_files':manifests,'reported_fields':reported})
    return rows


def batch_history():
    path=BENCH/'runs.jsonl'; groups=collections.defaultdict(list)
    if not path.exists():return []
    for number,line in enumerate(path.read_text().splitlines(),1):
        if not line.strip():continue
        r=json.loads(line);groups[r.get('version','unspecified')].append((number,r))
    return [{'version':k,'rows':len(v),'first_line':v[0][0],
             'outcomes':dict(collections.Counter(r.get('outcome','unknown') for _,r in v)),
             'reached':[r.get('reached') for _,r in v],
             'commits':sorted(set(r['commit'] for _,r in v if r.get('commit')))} for k,v in groups.items()]


def render(data):
    lines=['# Historical evidence inventory','',
        'Generated by `build_inventory.py`; the adjudicated narrative is in [EXPERIMENT-LEDGER.md](../EXPERIMENT-LEDGER.md).','',
        f"Snapshot cutoff (UTC): `{data['cutoff_utc']}`. Source existence is not evidence of success.",'',
        '## Coverage','',
        f"{len(data['commits'])} Git commits; {len(data['documents'])} documents; "
        f"{len(data['artifacts'])} immediate run/support directories; {len(data['batches'])} RC batch versions; "
        f"{len(data['sessions']['events'])} final-answer references in the three-thread ancestry.",'',
        '## Conversation lineage','',
        'Only user requests and assistant final-answer excerpts are indexed. No reasoning, tools, credentials, '
        'or unrelated conversations are exported. Parent records after the fork point are excluded. '
        'Session reports are claims; use result artifacts to verify. UTC timestamps can differ from journal dates.','']
    for s in data['sessions']['lineage']:
        lines.append(f"- `{s['id']}`: {link(s['path'])}; {s['final_answers']} answers, prefix through line {s['last_included_line']}; parent `{s['parent']}`.")
    lines+=['','Other DCSS-cwd sessions belong to manual gameplay/setup lineages; metadata was checked but their messages were not copied. See JSON for their paths.','',
            '## Documents and section-level index','']
    for doc in data['documents']:
        lines+=['### '+doc['path'],'',link(REPO/doc['path']),'']
        for s in doc['sections']:
            lines.append(f"- {link(REPO/doc['path'],clean(s['heading'],160),s['line'])}")
        lines.append('')
    lines+=['## Recorded RC batches','',
            'Each row groups the original runs.jsonl version, not an inferred promotion. Reached is not cleared; interventions and repeat counts require the journal.','',
            '| Version | Recorded rows | Outcomes | Reached |','| --- | ---: | --- | --- |']
    for b in data['batches']:
        lines.append(f"| {link(BENCH/'runs.jsonl',b['version'],b['first_line'])} | {b['rows']} | {clean(b['outcomes'])} | {clean(b['reached'])} |")
    lines+=['','## Preserved compact evidence files','',
            'Direct index of the RC and tactical evidence directories. Files are not additional independent trials; '
            'hashes and sizes are in inventory.json.','']
    for item in data['compact_evidence']:
        lines.append(f"- {link(REPO/item['path'],item['path'])} ({item['bytes']} bytes)")
    lines+=['','## Run and support directories','',
            'Shallow enumeration of every immediate directory, including failed attempts and worker/cache directories. '
            'Only root-level JSON manifests are listed; nested evaluation/cycle evidence may exist. '
            'Missing status is **unknown**, not failed or successful.','']
    for a in data['artifacts']:
        lines.append(f"- {link(REPO/a['path'],a['path'])} — {a['kind']}.")
        if a['reported_fields']:lines.append('  - Reported fields: `'+clean(json.dumps(a['reported_fields']),700)+'`')
        if a['root_json_files']:lines.append('  - Manifests: '+', '.join(link(REPO/p) for p in a['root_json_files']))
    lines+=['','## Commit chronology','',
            'Implementation commits and result commits are both retained; a commit title alone is not an experimental result.','',
            '| Commit | Author date | Subject |','| --- | --- | --- |']
    for c in data['commits']:lines.append(f"| `{c['sha'][:7]}` | {c['date']} | {clean(c['subject'])} |")
    return '\n'.join(lines).rstrip()+'\n'


def render_sessions(data):
    lines=['# Conversation conclusion index','',
           '[Back to ledger](../EXPERIMENT-LEDGER.md). Generated, abbreviated provenance—not adjudicated results. '
           'Open the source line for the full answer. Entries may describe plans, status questions, or corrections rather than experiments.','',
           'Parent sessions are cut at their recorded fork ordinals. Messages after the audit cutoff are excluded.','']
    for i,event in enumerate(data['sessions']['events'],1):
        q=event['request'] or {}
        lines += [f"## S{i:03d} — {event['timestamp']}",'',
                  f"Request: {q.get('text','(not available)')}",'',
                  f"Reported conclusion: {event['conclusion_excerpt']}",'',
                  f"Source: {link(event['path'],'session answer',event['line'])}; ordinal `{event['ordinal']}`.",'']
    return '\n'.join(lines).rstrip()+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--codex-root',type=Path,default=Path('/home/reeldata/.codex'))
    p.add_argument('--cutoff-utc',default='2026-09-14T13:31:09.234Z',help='exclusive cutoff before this audit request')
    args=p.parse_args()
    data={'schema':'dcss-experiment-evidence-index-v1','cutoff_utc':args.cutoff_utc,
          'generated_at':datetime.now(timezone.utc).isoformat(),'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
          'documents':documents(),'commits':commits(),'artifacts':artifacts(),'batches':batch_history(),
          'compact_evidence':compact_evidence(),
          'sessions':session_inventory(args.codex_root,args.cutoff_utc)}
    for name,body in [('inventory.json',json.dumps(data,indent=2)+'\n'),('SOURCES.md',render(data)),('SESSIONS.md',render_sessions(data))]:
        (HERE/name).write_text(body)
    print(json.dumps({'commits':len(data['commits']),'documents':len(data['documents']),
                      'artifact_roots':len(data['artifacts']),'batch_versions':len(data['batches']),
                      'session_answers':len(data['sessions']['events']),
                      'compact_evidence_files':len(data['compact_evidence'])}))


if __name__=='__main__':main()
