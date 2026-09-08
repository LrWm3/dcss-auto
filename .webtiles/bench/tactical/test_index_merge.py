import json
from pathlib import Path
import tempfile
import unittest
from index_cases import build


class MergeTests(unittest.TestCase):
    def test_namespaced_collections_keep_distinct_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);collections=[]
            for name in ('old','new'):
                collection=root/name/'collection';case=collection/'encounter-001';case.mkdir(parents=True)
                (case/'result.json').write_text(json.dumps(dict(id='encounter-001',seed=name,
                    case=str(case/'missing'),training_ready=False)))
                collections.append(collection)
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                build(collections,root/'rejected')
            self.assertFalse((root/'rejected').exists())
            index=build(collections,root/'combined',namespace=True)
            self.assertEqual([e['id'] for e in index['cases']],
                ['old/collection/encounter-001','new/collection/encounter-001'])
            self.assertEqual(index['transitions'],0)


if __name__=='__main__':unittest.main()
