import unittest
from gi_racesim.normalization.corners import parse_corner
from gi_racesim.normalization.progress import rank_band,progress_band

class ProgressTests(unittest.TestCase):
    def test_group_merge_not_advancement(self):
        roster=[1,2,3,4]
        a=rank_band(parse_corner('1-(2,3)-4'),4,declared_roster=roster)
        b=rank_band(parse_corner('(1,2,3)-4'),4,declared_roster=roster)
        self.assertEqual(a['min_rank'],4);self.assertEqual(b['min_rank'],4)
        self.assertFalse(progress_band(a,b)['confirmed_advanced'])
    def test_same_group_unknown_order_is_band(self):
        b=rank_band(parse_corner('(1,*2,3)-4'),1,declared_roster=[1,2,3,4])
        self.assertEqual((b['min_rank'],b['max_rank']),(2,3))
    def test_missing_widens_not_deletes(self):
        b=rank_band(parse_corner('1-2,3'),3,declared_roster=[1,2,3,4])
        self.assertEqual((b['min_rank'],b['max_rank']),(3,4))
    def test_confirmed_progress(self):
        a=rank_band(parse_corner('1-2,3,4'),4,declared_roster=[1,2,3,4])
        b=rank_band(parse_corner('4-1,2,3'),4,declared_roster=[1,2,3,4])
        self.assertTrue(progress_band(a,b)['confirmed_advanced'])

if __name__=='__main__':unittest.main()
