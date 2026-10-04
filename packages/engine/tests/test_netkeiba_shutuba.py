import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from gi_racesim.collector import CacheStore, Collector, Gate, HttpResponse, JST, MockTransport
from gi_racesim.normalization.netkeiba_shutuba import (
    ShutubaStructureError,
    parse_shutuba_html,
)


SOURCE_URL = 'https://race.netkeiba.com/race/shutuba.html?race_id=202605040211'
HTML = '''<!doctype html>
<html><head><title>合成レース(G2) 出馬表 | 2026年10月4日 東京11R レース情報(JRA)</title>
<script>var _shutuba_race_id = '202605040211';</script></head>
<body>
<div class="RaceList_Item02"><div class="RaceName">合成レース<span>G2</span></div>
<div class="RaceData01">15:45発走 / 芝1800m (左 A)</div>
<div class="RaceData02"><span>4回</span><span>東京</span><span>2日目</span><span>2頭</span></div></div>
<table class="Shutuba_Table RaceTable01 ShutubaTable"><thead><tr class="Header">
<th class="Waku">枠</th><th class="Umaban">馬番</th><th class="HorseInfo">馬名</th>
<th class="Barei">性齢</th><th>斤量</th><th class="Jockey">騎手</th>
<th class="Trainer">厩舎</th><th class="Weight">馬体重</th>
</tr></thead><tbody>
<tr class="HorseList"><td class="Waku1 Txt_C">1</td><td class="Umaban1 Txt_C">1</td>
<td class="HorseInfo"><a href="https://db.netkeiba.com/horse/2020000001">合成馬A</a></td>
<td class="Barei Txt_C">牡4</td><td class="Txt_C">57.0</td><td class="Jockey">騎手A</td><td class="Trainer">美浦調教師A</td><td class="Weight"></td></tr>
<tr class="HorseList"><td class="Waku1 Txt_C">1</td><td class="Umaban1 Txt_C">2</td>
<td class="HorseInfo"><a href="https://db.netkeiba.com/horse/2020000002">合成馬B</a></td>
<td class="Barei Txt_C">牝4</td><td class="Txt_C">55.0</td><td class="Jockey">騎手B</td><td class="Trainer">栗東調教師B</td><td class="Weight"></td></tr>
</tbody></table></body></html>'''.encode('utf-8')


class NetkeibaShutubaTests(unittest.TestCase):
    def test_parse_entry_page_without_following_links(self):
        result = parse_shutuba_html(HTML, source_url=SOURCE_URL,
                                    expected_race_id='202605040211')
        self.assertEqual(result['race']['course'], '東京')
        self.assertEqual(result['race']['distance_m'], 1800)
        self.assertEqual(result['race']['field_size'], 2)
        self.assertEqual(result['entries'][0]['horse_id'], '2020000001')
        self.assertEqual(result['entries'][1]['carried_kg'], 55.0)
        self.assertIsNone(result['entries'][0]['body_weight_kg'])
        self.assertEqual(result['quality']['missing_fields'],
                         ['results', 'laps', 'corners', 'odds_at_start'])

    def test_source_and_race_id_must_match(self):
        with self.assertRaises(ShutubaStructureError):
            parse_shutuba_html(HTML, source_url='http://race.netkeiba.com/race/shutuba.html?race_id=202605040211')
        with self.assertRaises(ShutubaStructureError):
            parse_shutuba_html(HTML, source_url='https://race.netkeiba.com/race/shutuba.html?race_id=202605040212')
        with self.assertRaises(ShutubaStructureError):
            parse_shutuba_html(HTML, expected_race_id='other')

    def test_missing_or_duplicate_structure_is_quarantined(self):
        cases = [
            HTML.replace(b'ShutubaTable', b'ChangedTable'),
            HTML.replace(b'<th class="Trainer">', b'<th class="Changed">'),
            HTML.replace(b'<td class="Umaban1 Txt_C">2</td>', b'<td class="Umaban1 Txt_C">1</td>'),
            HTML.replace('<span>2頭</span>'.encode(), '<span>3頭</span>'.encode()),
            HTML.replace(b'<td class="Txt_C">55.0</td>', b'<td class="Txt_C">bad</td>'),
            HTML.replace(b'https://db.netkeiba.com/horse/2020000001', b'https://evil.example/horse/2020000001'),
        ]
        for body in cases:
            with self.subTest(body=body), self.assertRaises(ShutubaStructureError):
                parse_shutuba_html(body, source_url=SOURCE_URL)

    def test_prediction_table_does_not_replace_entry_table(self):
        body = HTML.replace(
            b'</body>',
            b'<table class="Shutuba_Table PredictRap_Table"><tr class="HorseList">'
            b'<td class="Waku1">99</td></tr></table></body>',
        )
        result = parse_shutuba_html(body, source_url=SOURCE_URL)
        self.assertEqual(len(result['entries']), 2)

    def test_invalid_utf8_is_quarantined(self):
        with self.assertRaises(ShutubaStructureError):
            parse_shutuba_html(b'\xff', source_url=SOURCE_URL)

    def test_parse_cache_adapter_uses_saved_bytes_only(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / 'collector.sqlite3'
            raw = root / 'raw'
            now = datetime(2026, 9, 30, 8, tzinfo=JST)
            gate = Gate(db)
            transport = MockTransport(HttpResponse(200, HTML, {}, SOURCE_URL))
            try:
                gate.approve(now, 'synthetic source review')
                gate.enqueue(SOURCE_URL, kind='race_entry',
                             snapshot_key='synthetic', discovered_from='synthetic')
                collector = Collector(gate, transport=transport, cache=CacheStore(raw),
                                      response_parser=lambda body: True, now_fn=lambda: now)
                tick = collector.tick(now)
                parsed = collector.parse_cache(tick['raw_ref'], adapter='netkeiba-shutuba')
                self.assertEqual(transport.calls, 1)
                self.assertEqual(parsed[0]['state'], 'PARSED')
                normalized = parsed[0]['normalized']
                self.assertEqual(normalized['source']['raw_ref'], tick['raw_ref'])
                self.assertEqual(normalized['race']['field_size'], 2)
            finally:
                gate.close()


if __name__ == '__main__':
    unittest.main()
