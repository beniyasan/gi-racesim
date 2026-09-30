import unittest
from gi_racesim.normalization.corners import parse_corner, pair_observation, NotationError
from gi_racesim.normalization.timing import early_anchor, lap_endpoints, validate_laps, validate_lap_clock
from gi_racesim.normalization.asof import eligible_history

class CornerTests(unittest.TestCase):
    def test_groups(self):
        c=parse_corner('(2,*5,7)-1,4=3', [1,2,3,4,5,7])
        self.assertEqual(len(c.groups),4)
        self.assertEqual(c.groups[0].inner_to_outer,(2,5,7))
        self.assertEqual(c.groups[0].marked_leader,5)
    def test_gap_intervals(self):
        g=parse_corner('(2,*5,7)-1,4=3').groups
        self.assertEqual(g[1].gap_from_previous.lower_lengths,2)
        self.assertEqual(g[1].gap_from_previous.upper_lengths_exclusive,5)
        self.assertEqual(g[2].gap_from_previous.category,'one_to_under_two')
        self.assertEqual(g[3].gap_from_previous.category,'five_or_more')
        self.assertIsNone(g[3].gap_from_previous.upper_lengths_exclusive)
    def test_no_false_longitudinal_order(self):
        p=pair_observation(parse_corner('(2,*5,7)-1'),2,7)
        self.assertIsNone(p['a_before_b'])
        self.assertTrue(p['a_inside_b'])
    def test_leader(self):
        self.assertTrue(pair_observation(parse_corner('(2,*5,7)'),5,2)['a_before_b'])
    def test_between_groups(self):
        self.assertTrue(pair_observation(parse_corner('(2,7)-1'),7,1)['a_before_b'])
    def test_adjacency_unknown(self):
        g=parse_corner('(1,2)(3,4)').groups
        self.assertEqual(g[1].gap_from_previous.category,'unknown')
    def test_fullwidth(self):
        self.assertEqual(parse_corner('（２，＊５，７）－１').horses,(2,5,7,1))
    def test_duplicate(self):
        with self.assertRaises(NotationError): parse_corner('(1,2),1')
    def test_missing_roster(self):
        with self.assertRaises(NotationError): parse_corner('1,2',[1,2,3])
    def test_unknown_symbol(self):
        with self.assertRaises(NotationError): parse_corner('1/2')
    def test_multiple_leaders(self):
        with self.assertRaises(NotationError): parse_corner('(*1,*2)')
    def test_unclosed(self):
        with self.assertRaises(NotationError): parse_corner('(1,2')
    def test_trailing(self):
        with self.assertRaises(NotationError): parse_corner('1,')
    def test_empty(self):
        with self.assertRaises(NotationError): parse_corner('')
    def test_zero(self):
        with self.assertRaises(NotationError): parse_corner('0,1')
    def test_group_hyphen_invalid(self):
        with self.assertRaises(NotationError): parse_corner('(1-2)')
    def test_order_not_number_sort(self):
        self.assertEqual(parse_corner('(8,2,5)').groups[0].inner_to_outer,(8,2,5))
    def test_pair_validation(self):
        with self.assertRaises(ValueError): pair_observation(parse_corner('1,2'),1,3)

class TimingTests(unittest.TestCase):
    convention='first100_if_odd_hundred_then200'
    def test_1600(self): self.assertEqual(early_anchor(1600,94,34)['distance_m'],1000)
    def test_elapsed(self): self.assertEqual(early_anchor(1600,94,34)['elapsed_s'],60)
    def test_1200(self): self.assertEqual(early_anchor(1200,70,35)['distance_m'],600)
    def test_2500(self): self.assertEqual(lap_endpoints(2500,verified_convention=self.convention),list(range(100,2501,200)))
    def test_2400(self): self.assertEqual(lap_endpoints(2400,verified_convention=self.convention),list(range(200,2401,200)))
    def test_unknown_convention(self):
        with self.assertRaises(ValueError): lap_endpoints(2500,verified_convention='unknown')
    def test_bad_distance(self):
        with self.assertRaises(ValueError): lap_endpoints(2450,verified_convention=self.convention)
    def test_negative(self):
        with self.assertRaises(ValueError): early_anchor(1600,30,34)
    def test_nan(self):
        with self.assertRaises(ValueError): early_anchor(1600,float('nan'),34)
    def test_lap_count(self):
        with self.assertRaises(ValueError): validate_laps([200,400],[12.0],400)
    def test_lap_order(self):
        with self.assertRaises(ValueError): validate_laps([200,100],[12.0,12.0],100)
    def test_lap_missing(self):
        with self.assertRaises(ValueError): validate_laps([200],[None],200)
    def test_rounding(self):
        self.assertTrue(validate_lap_clock([200,400],[12.0,11.9],23.9)['within_tolerance'])

class AsOfTests(unittest.TestCase):
    target='2025-05-25T15:40:00+09:00'
    asof='2025-05-25T15:30:00+09:00'
    def rec(self):
        return dict(event_at='2025-04-01T15:40:00+09:00',available_at='2025-04-01T16:00:00+09:00',collected_at='2026-09-30T00:00:00+09:00',record_kind='historical_race_result')
    def test_late_collection_strict(self):
        self.assertFalse(eligible_history(self.rec(),target_start=self.target,as_of=self.asof,mode='prospective'))
    def test_retro(self):
        self.assertTrue(eligible_history(self.rec(),target_start=self.target,as_of=self.asof,mode='retrospective'))
    def test_current_race(self):
        r=self.rec();r['event_at']=self.target
        self.assertFalse(eligible_history(r,target_start=self.target,as_of=self.asof,mode='retrospective'))
    def test_future(self):
        r=self.rec();r['event_at']='2025-06-01T15:40:00+09:00'
        self.assertFalse(eligible_history(r,target_start=self.target,as_of=self.asof,mode='retrospective'))
    def test_lifetime(self):
        r=self.rec();r['record_kind']='current_lifetime_summary'
        self.assertFalse(eligible_history(r,target_start=self.target,as_of=self.asof,mode='retrospective'))
    def test_no_timezone(self):
        with self.assertRaises(ValueError): eligible_history(self.rec(),target_start=self.target,as_of='2025-05-25T15:30:00',mode='retrospective')
    def test_observed_in_time(self):
        r=self.rec();r['collected_at']='2025-04-01T17:00:00+09:00'
        self.assertTrue(eligible_history(r,target_start=self.target,as_of=self.asof,mode='prospective'))
    def test_unknown_availability(self):
        r=self.rec();r['available_at']=None;r['collected_at']='2025-04-01T17:00:00+09:00'
        self.assertFalse(eligible_history(r,target_start=self.target,as_of=self.asof,mode='prospective'))

if __name__=='__main__': unittest.main()
