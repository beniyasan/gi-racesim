import copy
import unittest
from gi_racesim.datasets.example_builder import build_example,freeze_manifest

class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.k=dict(race_id='R',target_start='2025-06-01T15:40:00+09:00',
                    as_of='2025-06-01T15:30:00+09:00',mode='retrospective',
                    condition={'course':'mock','surface':'turf','distance_m':1600},
                    entries=[{'horse_id':f'H{i}','gate_no':i,'finish_rank':5-i} for i in range(1,5)],
                    history_records=[],
                    corner_observations=[{'checkpoint':'3C','notation':'(1,*2,3)-4'}],
                    lap_observation={'complete':True,'seconds':[12]*8,'endpoints_m':list(range(200,1601,200))})
    def test_x_has_no_target_outcome(self):
        e=build_example(**self.k)
        self.assertTrue(all('finish_rank' not in r['entry'] for r in e['X']['runners']))
    def test_within_group_unknown_front(self):
        e=build_example(**self.k);p=next(p for p in e['Y']['corners'][0]['pairs'] if (p['a'],p['b'])==(1,3))
        self.assertIsNone(p['a_before_b']); self.assertFalse(p['front_mask']);self.assertTrue(p['inside_mask'])
    def test_future_result_cannot_change_x(self):
        a=build_example(**self.k)['X']
        self.k['history_records']=[{'horse_id':'H1','race_id':'FUTURE','record_kind':'historical_race_result',
                                    'event_at':'2025-07-01T00:00:00+09:00'}]
        self.assertEqual(a,build_example(**self.k)['X'])
    def test_current_lifetime_stats_excluded(self):
        self.k['history_records']=[{'horse_id':'H1','race_id':'P','record_kind':'lifetime_summary',
                                    'event_at':'2025-05-01T00:00:00+09:00'}]
        self.assertEqual(build_example(**self.k)['X']['runners'][0]['history_count'],0)
    def test_prospective_requires_collection(self):
        self.k['mode']='prospective'
        self.k['history_records']=[{'horse_id':'H1','race_id':'P','record_kind':'historical_race_result',
                                    'event_at':'2025-05-01T00:00:00+09:00',
                                    'available_at':'2025-05-01T18:00:00+09:00',
                                    'collected_at':'2026-09-30T00:00:00+09:00'}]
        self.assertEqual(build_example(**self.k)['X']['runners'][0]['history_count'],0)
    def test_last_start_all_distances(self):
        self.k['history_records']=[{'horse_id':'H1','race_id':'P','record_kind':'historical_race_result',
                                    'event_at':'2025-05-18T15:30:00+09:00','distance_m':2400}]
        r=build_example(**self.k)['X']['runners'][0]
        self.assertEqual(r['days_since_latest_observed_start'],14)
        self.assertFalse(r['history_complete'])
    def test_no_lap_no_conditional_teacher(self):
        self.k['lap_observation']=None
        r=build_example(**self.k)['training_routes']
        self.assertFalse(r['conditional_corner_loss']);self.assertTrue(r['unconditional_corner_auxiliary'])
    def test_unknown_corner_not_empty_field(self):
        self.k['corner_observations']=[{'checkpoint':'3C','notation':None}]
        self.assertFalse(build_example(**self.k)['Y']['corners'][0]['observed'])
    def test_missing_runner_not_prescribed_dnf(self):
        self.k['corner_observations']=[{'checkpoint':'3C','notation':'1-2,3'}]
        e=build_example(**self.k)
        self.assertEqual(len(e['X']['runners']),4)
        self.assertEqual(e['Y']['corners'][0]['unobserved_gate_numbers'],[4])
        self.assertFalse(e['training_routes']['conditional_corner_loss'])
    def test_entry_order_not_finishing_order(self):
        a=build_example(**self.k)['X']
        self.k['entries'].reverse()
        self.assertEqual(a,build_example(**self.k)['X'])
    def test_source_manifest_immutable_content(self):
        kw=dict(sources=[{'source_id':'a','sha256':'a'*64}],splits={'train':['r1'],'test':['r2']},
                parser_version='p1',feature_version='f1')
        a=freeze_manifest(**kw)
        kw['sources'][0]['sha256']='b'*64
        self.assertNotEqual(a['dataset_hash'],freeze_manifest(**kw)['dataset_hash'])
    def test_split_overlap_rejected(self):
        with self.assertRaises(ValueError):
            freeze_manifest(sources=[],splits={'train':['r'],'test':['r']},parser_version='p',feature_version='f')
    def test_duplicate_source_rejected(self):
        with self.assertRaises(ValueError):
            freeze_manifest(sources=[{'source_id':'s','sha256':'a'*64}]*2,splits={},parser_version='p',feature_version='f')
    def test_duplicate_history_version_rejected(self):
        r={'horse_id':'H1','race_id':'P','record_kind':'historical_race_result','event_at':'2025-05-01T00:00:00+09:00'}
        self.k['history_records']=[r,r.copy()]
        with self.assertRaises(ValueError):build_example(**self.k)
    def test_invalid_asof(self):
        self.k['as_of']=self.k['target_start']
        with self.assertRaises(ValueError):build_example(**self.k)

if __name__=='__main__':unittest.main()
