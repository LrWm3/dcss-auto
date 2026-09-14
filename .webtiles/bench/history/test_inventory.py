"""Read-only checks for the persisted historical evidence index.

Run from the repository root:
  /usr/bin/python3 -m unittest discover -s .webtiles/bench/history -v
Regenerate the index after changing its source documents.
"""
import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

import build_inventory as inventory


class InventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((inventory.HERE / 'inventory.json').read_text())

    def test_document_hashes_and_sections(self):
        for doc in self.data['documents']:
            path = inventory.REPO / doc['path']
            raw = path.read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), doc['sha256'], str(path))
            lines = raw.decode(errors='replace').splitlines()
            for section in doc['sections']:
                self.assertEqual(lines[section['line'] - 1].lstrip('# '), section['heading'])

    def test_commit_and_batch_coverage(self):
        commits = subprocess.check_output(
            ['git', 'rev-list', '--reverse', self.data['git_head']], cwd=inventory.REPO, text=True).splitlines()
        self.assertEqual(commits, [c['sha'] for c in self.data['commits']])
        self.assertEqual(inventory.batch_history(), self.data['batches'])

    def test_compact_evidence_coverage_and_hashes(self):
        self.assertEqual(inventory.compact_evidence(), self.data['compact_evidence'])

    def test_local_links(self):
        paths = [inventory.BENCH / 'EXPERIMENT-LEDGER.md',
                 inventory.HERE / 'SOURCES.md', inventory.HERE / 'SESSIONS.md']
        for path in paths:
            for match in re.finditer(r'\]\((<[^>]+>|[^)]+)\)', path.read_text()):
                target = match.group(1).strip('<>')
                if target.startswith(('https:', 'http:', '#')):
                    continue
                target = re.sub(r':\d+$', '', target.split('#')[0])
                resolved = Path(target) if target.startswith('/') else path.parent / target
                self.assertTrue(resolved.exists(), f'{path}: {target}')

    def test_session_prefix_and_export_scope(self):
        events = self.data['sessions']['events']
        lineage = self.data['sessions']['lineage']
        self.assertEqual(lineage[-1]['id'], inventory.CURRENT_THREAD)
        self.assertEqual(len({(e['thread'], e['line']) for e in events}), len(events))
        for index, session in enumerate(lineage):
            if index:
                self.assertEqual(session['parent'], lineage[index - 1]['id'])
            selected = {e['line']: e for e in events if e['thread'] == session['id']}
            digest = hashlib.sha256()
            found = set()
            with Path(session['path']).open('rb') as stream:
                for number, raw in enumerate(stream, 1):
                    if number > session['last_included_line']:
                        break
                    digest.update(raw)
                    row = json.loads(raw)
                    self.assertLess(row.get('timestamp', ''), self.data['cutoff_utc'])
                    if session['ordinal_exclusive'] is not None:
                        self.assertLess(row.get('ordinal', -1), session['ordinal_exclusive'])
                    if number not in selected:
                        continue
                    found.add(number)
                    payload = row['payload']
                    self.assertEqual(row['type'], 'response_item')
                    self.assertEqual(payload['role'], 'assistant')
                    self.assertIn(payload['phase'], ('final', 'final_answer'))
                    full = '\n'.join(c.get('text', '') for c in payload.get('content', [])
                                     if isinstance(c, dict))
                    self.assertEqual(inventory.clean(full, 650), selected[number]['conclusion_excerpt'])
            self.assertEqual(found, set(selected))
            self.assertEqual(digest.hexdigest(), session['included_prefix_sha256'])
        included = {s['id'] for s in lineage}
        self.assertTrue(included.isdisjoint(
            s['id'] for s in self.data['sessions']['excluded_related_sessions']))

    def test_stable_session_rebuild(self):
        rebuilt = inventory.session_inventory(Path('/home/reeldata/.codex'), self.data['cutoff_utc'])
        self.assertEqual(rebuilt['lineage'], self.data['sessions']['lineage'])
        self.assertEqual(rebuilt['events'], self.data['sessions']['events'])


if __name__ == '__main__':
    unittest.main()
