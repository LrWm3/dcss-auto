import copy
import unittest
from train_teacher import imitate
from train_encounters import value


class TeacherTests(unittest.TestCase):
    def test_learns_geometry_and_respects_mask(self):
        rows=[dict(features={'bias':1,'x':x},allowed=['e','w'],action=a)
              for x,a in ((1,'w'),(-1,'e'))]
        model,accuracy=imitate(rows)
        self.assertEqual(accuracy,1)
        self.assertEqual(set(model),{'e','w'})
        for row in rows:
            self.assertEqual(max(row['allowed'],key=lambda a:value(model,a,row['features'])),row['action'])

    def test_fit_is_deterministic_and_does_not_mutate_demonstrations(self):
        rows=[dict(features={'bias':1},allowed=['baseline','wait'],action='wait')]
        before=copy.deepcopy(rows)
        self.assertEqual(imitate(rows),imitate(rows))
        self.assertEqual(rows,before)

    def test_empty_and_illegal_rejected(self):
        with self.assertRaises(ValueError): imitate([])
        with self.assertRaises(ValueError):
            imitate([dict(features={'bias':1},allowed=['wait'],action='e')])


if __name__=='__main__': unittest.main()
