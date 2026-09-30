import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from gi_racesim.collector import (
    CacheStore,
    Collector,
    Gate,
    HttpResponse,
    JST,
    MockTransport,
    Policy,
    TransportError,
)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db_path = root / 'state.sqlite3'
        self.cache_path = root / 'raw'
        self.gate = Gate(self.db_path)
        self.now = datetime(2026, 9, 30, 8, tzinfo=JST)

    def tearDown(self):
        self.gate.close()
        self.tmp.cleanup()

    def collector(self, transport=None):
        return Collector(self.gate, transport=transport,
                          cache=CacheStore(self.cache_path))

    def setup_task(self, n=1):
        self.gate.approve(self.now, 'synthetic source review')
        for i in range(n):
            self.gate.enqueue(f'https://race.netkeiba.com/mock/{i}',
                              discovered_from='synthetic fixture')

    def test_default_transport_is_disabled_without_consuming_budget(self):
        self.setup_task()
        result = self.collector().tick(self.now)
        self.assertEqual(result['state'], 'EXTERNAL_DISABLED')
        self.assertEqual(self.gate.status()['total_reserved_requests'], 0)

    def test_one_mock_request_saves_html_and_metadata(self):
        self.setup_task()
        transport = MockTransport(HttpResponse(
            200, b'<html><title>synthetic</title><body>fixture</body></html>',
            {'Content-Type': 'text/html'},
            'https://race.netkeiba.com/mock/0'))
        collector = self.collector(transport)
        result = collector.tick(self.now)
        self.assertEqual(result['state'], 'OK')
        self.assertEqual(transport.calls, 1)
        saved = self.gate.response(result['raw_ref'])
        self.assertIsNotNone(saved)
        self.assertEqual(saved['requested_url'], 'https://race.netkeiba.com/mock/0')
        self.assertEqual(saved['status_code'], 200)
        self.assertTrue(Path(saved['path']).is_file())
        parsed = collector.parse_cache(result['raw_ref'])
        self.assertEqual(parsed[0]['state'], 'PARSED')
        self.assertEqual(parsed[0]['title'], 'synthetic')
        self.assertEqual(transport.calls, 1, 'parse-cache must not communicate')

    def test_waiting_window_and_pause_do_not_call_transport(self):
        self.setup_task(2)
        transport = MockTransport([
            HttpResponse(200, b'first'),
            HttpResponse(200, b'second'),
        ])
        collector = self.collector(transport)
        collector.tick(self.now)
        self.assertEqual(collector.tick(self.now + timedelta(seconds=1))['state'], 'WAIT')
        self.assertEqual(transport.calls, 1)
        self.assertEqual(collector.tick(self.now + timedelta(hours=15))['state'], 'OUTSIDE_WINDOW')
        self.assertEqual(transport.calls, 1)
        self.gate.pause(self.now + timedelta(hours=15), 'manual review')
        self.assertEqual(collector.tick(self.now + timedelta(days=1))['state'], 'PAUSED')
        self.assertEqual(transport.calls, 1)

    def test_resume_does_not_reset_next_at_or_budget(self):
        self.setup_task(2)
        transport = MockTransport([
            HttpResponse(200, b'first'),
            HttpResponse(200, b'second'),
        ])
        collector = self.collector(transport)
        collector.tick(self.now)
        before = self.gate.status()
        self.gate.pause(self.now + timedelta(seconds=1), 'operator pause')
        self.gate.resume(self.now + timedelta(seconds=2), 'review complete')
        after = self.gate.status()
        self.assertEqual(after['total_reserved_requests'], before['total_reserved_requests'])
        self.assertEqual(after['next_at'], before['next_at'])
        self.assertEqual(collector.tick(self.now + timedelta(seconds=121))['state'], 'OK')
        self.assertEqual(transport.calls, 2)

    def test_redirect_is_recorded_without_follow_up(self):
        self.setup_task()
        transport = MockTransport(HttpResponse(
            302, b'', {'Location': 'https://race.netkeiba.com/other'},
            'https://race.netkeiba.com/mock/0'))
        result = self.collector(transport).tick(self.now)
        self.assertEqual(result['state'], 'REDIRECT')
        self.assertEqual(transport.calls, 1)
        self.assertEqual(self.gate.status()['tasks']['REDIRECT_REVIEW'], 1)

    def test_blocked_response_pauses_source_group(self):
        self.setup_task(2)
        transport = MockTransport(HttpResponse(403, b'access denied'))
        collector = self.collector(transport)
        result = collector.tick(self.now)
        self.assertEqual(result['state'], 'BLOCKED')
        self.assertEqual(transport.calls, 1)
        self.assertEqual(collector.tick(self.now + timedelta(days=1))['state'], 'PAUSED')
        self.assertEqual(transport.calls, 1)

    def test_429_and_auth_challenge_are_source_wide_stop_signals(self):
        for response in (HttpResponse(429, b'too many requests'),
                         HttpResponse(200, b'login', {'WWW-Authenticate': 'Basic'})):
            with self.subTest(status=response.status_code):
                self.gate.close()
                path = Path(self.tmp.name) / f'blocked-{response.status_code}.sqlite3'
                self.gate = Gate(path)
                self.now = datetime(2026, 9, 30, 8, tzinfo=JST)
                self.setup_task()
                transport = MockTransport(response)
                result = self.collector(transport).tick(self.now)
                self.assertEqual(result['state'], 'BLOCKED')
                self.assertEqual(self.gate.status()['paused'], 'blocked')

    def test_transport_failure_is_deferred_without_same_tick_retry(self):
        self.setup_task()
        transport = MockTransport([TransportError('timeout'), HttpResponse(200, b'retry')])
        collector = self.collector(transport)
        first = collector.tick(self.now)
        self.assertEqual(first['state'], 'TEMPORARY')
        self.assertEqual(transport.calls, 1)
        self.assertEqual(collector.tick(self.now + timedelta(hours=1))['state'], 'NO_READY_TASK')
        self.assertEqual(transport.calls, 1)
        self.assertEqual(collector.tick(self.now + timedelta(hours=6))['state'], 'OK')
        self.assertEqual(transport.calls, 2)

    def test_parser_structure_change_quarantines_without_refetch(self):
        self.setup_task(2)
        transport = MockTransport([HttpResponse(200, b'changed markup'),
                                   HttpResponse(200, b'never used')])

        def parser(_body):
            raise RuntimeError('required result table missing')

        collector = Collector(self.gate, transport=transport,
                              cache=CacheStore(self.cache_path),
                              response_parser=parser)
        result = collector.tick(self.now)
        self.assertEqual(result['state'], 'PARSE_ERROR')
        self.assertEqual(transport.calls, 1)
        self.assertEqual(self.gate.status()['tasks']['QUARANTINED'], 1)
        self.assertEqual(self.gate.status()['paused'], 'parse_schema_review')
        self.assertEqual(collector.tick(self.now + timedelta(days=1))['state'], 'PAUSED')
        self.assertEqual(transport.calls, 1)

    def test_crash_keeps_active_token_across_restart(self):
        self.setup_task()
        permit = self.gate.claim(self.now)
        self.gate.close()
        self.gate = Gate(self.db_path)
        collector = self.collector(MockTransport(HttpResponse(200, b'never used')))
        self.assertEqual(collector.tick(self.now + timedelta(days=1))['state'],
                         'IN_FLIGHT_OR_UNCERTAIN')
        self.assertEqual(collector.transport.calls, 0)
        with self.assertRaises(ValueError):
            self.gate.resume(self.now + timedelta(days=1), 'not safe yet')
        self.gate.abandon(permit['token'], self.now + timedelta(days=1),
                          'worker stopped; response uncertain')
        self.assertEqual(self.gate.status()['tasks']['UNCERTAIN'], 1)

    def test_small_budget_is_enforced_without_transport_calls(self):
        self.gate.close()
        self.gate = Gate(self.db_path.with_name('small.sqlite3'),
                         Policy(daily_requests=1, rolling24_requests=1))
        self.setup_task(2)
        transport = MockTransport([HttpResponse(200, b'one'), HttpResponse(200, b'two')])
        collector = self.collector(transport)
        collector.tick(self.now)
        self.assertEqual(collector.tick(self.now + timedelta(hours=1))['state'], 'DAILY_LIMIT')
        self.assertEqual(transport.calls, 1)


if __name__ == '__main__':
    unittest.main()
