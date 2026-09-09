import unittest
from screen_training_options import verify


class ScreenTests(unittest.TestCase):
    def test_rejects_validation_and_test_before_file_access(self):
        entry=dict(id='x',seed='123',split_group='123',eligible=True,case='unused')
        for partition in ('validation','test',None):
            with self.assertRaisesRegex(ValueError,'Training seeds only'):
                verify([entry],{'123':partition})

    def test_rejects_empty_duplicates_and_unverified(self):
        with self.assertRaises(ValueError): verify([],{})
        e=dict(id='x',seed='123',split_group='123',eligible=False)
        with self.assertRaisesRegex(ValueError,'Duplicate'): verify([e,e],{'123':'train'})
        with self.assertRaisesRegex(ValueError,'Unverified'): verify([e],{'123':'train'})


if __name__=='__main__': unittest.main()
