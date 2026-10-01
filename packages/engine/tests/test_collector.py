import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from gi_racesim.collector import (
    CacheStore,
    Collector,
    Gate,
    HttpResponse,
    JST,
    MockTransport,
    Policy,
    TransportError,
    UrllibTransport,
    require_reviewed_source_structure,
)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db_path = root / 'state.sqlite3'
        self.cache_path = root / 'raw'
        self.gate = Gate(self.db_path)
        self.now = datetime(2026, 9, 30, 8, tzinfo=JST)
        network = patch('socket.create_connection', side_effect=AssertionError('network forbidden'))
        network.start()
        self.addCleanup(network.stop)

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

    def test_auth_signal_wins_over_redirect_classification(self):
        self.setup_task(2)
        transport = MockTransport(HttpResponse(
            302, b'login',
            {'Location': 'https://race.netkeiba.com/login',
             'WWW-Authenticate': 'Basic'},
            'https://race.netkeiba.com/mock/0'))
        collector = self.collector(transport)
        result = collector.tick(self.now)
        self.assertEqual(result['state'], 'BLOCKED')
        self.assertEqual(self.gate.status()['paused'], 'blocked')
        self.assertEqual(transport.calls, 1)
        self.assertEqual(collector.tick(self.now + timedelta(days=1))['state'], 'PAUSED')
        self.assertEqual(transport.calls, 1)

    def test_auth_and_challenge_signals_override_status_and_changed_url(self):
        from gi_racesim.collector import classify_response
        responses = (
            HttpResponse(307, b'', {'X-Challenge': 'required'}),
            HttpResponse(304, b'', {'WWW-Authenticate': 'Basic'}),
            HttpResponse(403, b'', {}, 'https://race.netkeiba.com/login'),
            HttpResponse(200, b'captcha', {}, 'https://race.netkeiba.com/login'),
        )
        for response in responses:
            with self.subTest(response=response):
                self.assertEqual(classify_response(response, 'https://race.netkeiba.com/mock'), 'blocked')

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

    def test_default_html_structure_validator_rejects_plain_success(self):
        self.setup_task()
        transport = MockTransport(HttpResponse(200, b'login page without markup'))
        collector = Collector(self.gate, transport=transport,
                              cache=CacheStore(self.cache_path),
                              response_parser=require_reviewed_source_structure)
        result = collector.tick(self.now)
        self.assertEqual(result['state'], 'PARSE_ERROR')
        self.assertEqual(self.gate.status()['paused'], 'parse_schema_review')

    def test_unreviewed_validator_rejects_complete_html_with_arbitrary_table(self):
        from gi_racesim.collector import StructureChange
        with self.assertRaises(StructureChange):
            require_reviewed_source_structure(b'<html><body><table><tr><td>Sign in</td></tr>'
                                               b'</table></body></html>')

    def test_external_transport_rejects_synthetic_timestamp(self):
        self.setup_task()
        collector = Collector(self.gate,
                              transport=UrllibTransport(allow_external=True),
                              cache=CacheStore(self.cache_path))
        with patch.object(collector.transport, 'fetch') as fetch:
            with self.assertRaisesRegex(ValueError, 'synthetic timestamp'):
                collector.tick(self.now)
            fetch.assert_not_called()
        self.assertEqual(self.gate.status()['total_reserved_requests'], 0)

    def test_external_transport_rejects_injected_clock(self):
        self.setup_task()
        for enabled in (False, True):
            with self.subTest(enabled=enabled), self.assertRaisesRegex(ValueError, 'synthetic clock'):
                Collector(self.gate, transport=UrllibTransport(allow_external=enabled),
                          cache=CacheStore(self.cache_path), now_fn=lambda: self.now)
        self.assertEqual(self.gate.status()['total_reserved_requests'], 0)

    def test_unclassified_transport_cannot_use_synthetic_time(self):
        class ExternalAdapter:
            enabled = True

            def fetch(self, _url):
                raise AssertionError('must fail before transport is called')

        self.setup_task()
        collector = self.collector(ExternalAdapter())
        with self.assertRaisesRegex(ValueError, 'synthetic timestamp'):
            collector.tick(self.now)
        self.assertEqual(self.gate.status()['total_reserved_requests'], 0)

    def test_external_completion_wait_starts_after_response(self):
        self.setup_task(2)
        clock = [self.now, self.now + timedelta(seconds=30),
                 self.now + timedelta(seconds=149), self.now + timedelta(seconds=150),
                 self.now + timedelta(seconds=155)]
        transport = UrllibTransport(allow_external=True)
        with patch('gi_racesim.collector.service._wall_clock', side_effect=clock):
            collector = Collector(self.gate, transport=transport, cache=CacheStore(self.cache_path),
                                  response_parser=lambda body: True)
            with patch.object(transport, 'fetch', return_value=HttpResponse(200, b'synthetic')) as fetch:
                self.assertEqual(collector.tick()['state'], 'OK')
                self.assertEqual(self.gate.status()['next_at'], clock[3].timestamp())
                self.assertEqual(collector.tick()['state'], 'WAIT')
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(collector.tick()['state'], 'OK')
                self.assertEqual(fetch.call_count, 2)

    def test_clock_regression_during_live_response_preserves_active_token(self):
        self.setup_task(2)
        transport = UrllibTransport(allow_external=True)
        clock = [self.now, self.now - timedelta(seconds=1)]
        with patch('gi_racesim.collector.service._wall_clock', side_effect=clock):
            collector = self.collector(transport)
            with patch.object(transport, 'fetch', return_value=HttpResponse(200, b'synthetic')) as fetch:
                with self.assertRaisesRegex(ValueError, 'clock moved backwards'):
                    collector.tick()
                fetch.assert_called_once()
        self.assertIsNotNone(self.gate.status()['active_token'])
        self.assertEqual(self.gate.status()['total_reserved_requests'], 1)
        self.assertEqual(self.gate.claim(self.now + timedelta(days=1))['state'], 'IN_FLIGHT_OR_UNCERTAIN')

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
