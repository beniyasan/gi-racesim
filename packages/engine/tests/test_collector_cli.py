import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from gi_racesim.collector.cli import main


class CollectorCliTests(unittest.TestCase):
    def test_cli_mock_tick_and_parse_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / 'state.sqlite3'
            raw = root / 'raw'
            page = root / 'page.html'
            page.write_text('<title>cli</title><p>fixture</p>', encoding='utf-8')
            common = ['--db', str(db), '--cache-dir', str(raw),
                      '--now', '2026-09-30T08:00:00+09:00']
            self.assertEqual(main(common + ['approve', '--note', 'synthetic']), 0)
            self.assertEqual(main(common + ['enqueue', 'https://race.netkeiba.com/cli',
                                             '--discovered-from', 'synthetic']), 0)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(common + ['tick', '--mock-html', str(page)]), 0)
            tick = json.loads(output.getvalue())
            self.assertEqual(tick['transport_calls'], 1)
            self.assertTrue(tick['raw_ref'].startswith('cache:'))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(common + ['parse-cache']), 0)
            parsed = json.loads(output.getvalue())
            self.assertEqual(parsed['entries'][0]['state'], 'PARSED')

    def test_cli_default_tick_does_not_enable_http(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common = ['--db', str(root / 'state.sqlite3'),
                      '--cache-dir', str(root / 'raw'),
                      '--now', '2026-09-30T08:00:00+09:00']
            main(common + ['approve', '--note', 'synthetic'])
            main(common + ['enqueue', 'https://race.netkeiba.com/cli',
                            '--discovered-from', 'synthetic'])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(common + ['tick']), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result['state'], 'EXTERNAL_DISABLED')
            self.assertEqual(result['transport_calls'], 0)


if __name__ == '__main__':
    unittest.main()
