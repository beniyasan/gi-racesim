import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from gi_racesim.collector import Gate, HttpResponse, JST, UrllibTransport
from gi_racesim.collector.cli import main
from gi_racesim.collector.service import StructureChange, validate_synthetic_html_structure


SYNTHETIC_HTML = '''<html><head><title>cli</title></head><body>
<table data-giracesim="synthetic-result-v1">
<tr><th data-field="horse">Horse</th><th data-field="finish">Finish</th></tr>
<tr><td data-field="horse">Synthetic A</td><td data-field="finish">1</td></tr>
</table></body></html>'''


class CollectorCliTests(unittest.TestCase):
    def setUp(self):
        # A test failure must never fall through to real HTTP.
        network = patch('socket.create_connection', side_effect=AssertionError('network forbidden'))
        network.start()
        self.addCleanup(network.stop)

    def test_synthetic_structure_requires_declared_result_columns(self):
        validate_synthetic_html_structure(SYNTHETIC_HTML.encode('utf-8'))
        changed = (SYNTHETIC_HTML.replace('data-field="finish"', 'data-field="unknown"'),
                   SYNTHETIC_HTML.replace('synthetic-result-v1', 'unknown-v2'),
                   SYNTHETIC_HTML.replace('</table>', ''),
                   '<html><body>Result table removed</body></html>')
        for body in changed:
            with self.subTest(body=body), self.assertRaises(StructureChange):
                validate_synthetic_html_structure(body.encode('utf-8'))

    def test_cli_mock_tick_and_parse_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / 'state.sqlite3'
            raw = root / 'raw'
            page = root / 'page.html'
            page.write_text(SYNTHETIC_HTML, encoding='utf-8')
            common = ['--db', str(db), '--cache-dir', str(raw),
                      '--now', '2026-09-30T08:00:00+09:00']
            self.assertEqual(main(common + ['approve', '--note', 'synthetic']), 0)
            self.assertEqual(main(common + ['enqueue', 'https://race.netkeiba.com/cli',
                                             '--discovered-from', 'synthetic']), 0)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(common + ['tick', '--mock-html', str(page)]), 0)
            tick = json.loads(output.getvalue())
            self.assertEqual(tick['state'], 'OK')
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

    def test_cli_rejects_synthetic_time_for_external_tick(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            common = ['--db', str(root / 'state.sqlite3'),
                      '--cache-dir', str(root / 'raw')]
            clock = ['--now', '2026-09-30T08:00:00+09:00']
            for options in (clock + ['tick', '--allow-external'],
                            ['tick', '--allow-external'] + clock):
                with self.subTest(options=options), patch.object(UrllibTransport, 'fetch') as fetch:
                    with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                        main(common + options)
                    self.assertEqual(error.exception.code, 2)
                    fetch.assert_not_called()
                    self.assertFalse((root / 'state.sqlite3').exists())
                    self.assertFalse((root / 'raw').exists())

    def test_cli_rejects_mixed_mock_and_external_modes_before_io(self):
        with patch('gi_racesim.collector.cli.Gate') as gate:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(['tick', '--allow-external', '--mock-html', 'unused.html'])
            self.assertEqual(error.exception.code, 2)
            gate.assert_not_called()

    def test_cli_structural_change_is_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / 'state.sqlite3'
            raw = root / 'raw'
            page = root / 'page.html'
            page.write_text('<html><body><h1>Sign in</h1><table><tr>'
                            '<td>Result unavailable</td></tr></table></body></html>', encoding='utf-8')
            common = ['--db', str(db), '--cache-dir', str(raw),
                      '--now', '2026-09-30T08:00:00+09:00']
            main(common + ['approve', '--note', 'synthetic'])
            main(common + ['enqueue', 'https://race.netkeiba.com/cli',
                            '--discovered-from', 'synthetic'])
            main(common + ['enqueue', 'https://db.netkeiba.com/other',
                            '--discovered-from', 'synthetic'])
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(common + ['tick', '--mock-html', str(page)]), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result['state'], 'PARSE_ERROR')
            self.assertEqual(result['transport_calls'], 1)
            gate = Gate(db)
            try:
                self.assertEqual(gate.status()['paused'], 'parse_schema_review')
                self.assertEqual(gate.status()['tasks'], {'QUARANTINED': 1, 'PENDING': 1})
                self.assertEqual(Path(gate.response(result['raw_ref'])['path']).read_bytes(),
                                 page.read_bytes())
            finally:
                gate.close()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(common + ['tick', '--mock-html', str(page)]), 0)
            again = json.loads(output.getvalue())
            self.assertEqual(again['state'], 'PAUSED')
            self.assertEqual(again['transport_calls'], 0)

    def test_cli_quarantines_live_html_without_reviewed_source_validator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / 'state.sqlite3'
            common = ['--db', str(db), '--cache-dir', str(root / 'raw')]
            start = datetime(2026, 9, 30, 8, tzinfo=JST)
            gate = Gate(db)
            gate.approve(start, 'synthetic review')
            gate.enqueue('https://race.netkeiba.com/cli', discovered_from='synthetic')
            gate.enqueue('https://db.netkeiba.com/other', discovered_from='synthetic')
            gate.close()
            # Even the synthetic fixture must not be accepted as a live-source format.
            response = HttpResponse(200, SYNTHETIC_HTML.encode('utf-8'))
            clock = [start, start + timedelta(seconds=30), start + timedelta(days=1)]
            with patch.object(UrllibTransport, 'fetch', return_value=response) as fetch:
                with patch('gi_racesim.collector.service._wall_clock', side_effect=clock):
                    first, second = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(first):
                        self.assertEqual(main(common + ['tick', '--allow-external']), 0)
                    with contextlib.redirect_stdout(second):
                        self.assertEqual(main(common + ['tick', '--allow-external']), 0)
                fetch.assert_called_once()
            result = json.loads(first.getvalue())
            self.assertEqual(result['state'], 'PARSE_ERROR')
            self.assertIn('no reviewed source', result['error'])
            self.assertEqual(json.loads(second.getvalue())['transport_calls'], 0)
            gate = Gate(db)
            try:
                self.assertEqual(gate.status()['paused'], 'parse_schema_review')
                self.assertEqual(gate.status()['total_reserved_requests'], 1)
                self.assertEqual(Path(gate.response(result['raw_ref'])['path']).read_bytes(), response.body)
            finally:
                gate.close()


if __name__ == '__main__':
    unittest.main()
