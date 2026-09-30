import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime,timedelta
from pathlib import Path
from gi_racesim.collector.gate import Gate,Policy,JST

class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'queue.sqlite'
        self.g=Gate(self.path)
        self.now=datetime(2026,9,30,8,tzinfo=JST)
    def tearDown(self):
        self.g.close(); self.tmp.cleanup()
    def setup_task(self,n=2):
        self.g.approve(self.now,'offline test')
        for i in range(n):
            self.g.enqueue(f'https://race.netkeiba.com/mock/{i}',discovered_from='synthetic')
    def finish(self,p,now=None,**kw):
        self.g.finish(p['token'],now or self.now,outcome=kw.pop('outcome','ok'),
                      raw_ref=kw.pop('raw_ref','mock body'),**kw)
    def test_review_required(self):
        self.assertEqual(self.g.claim(self.now)['state'],'SOURCE_REVIEW_REQUIRED')
    def test_empty_review_rejected(self):
        with self.assertRaises(ValueError): self.g.approve(self.now,' ')
    def test_allowlist(self):
        with self.assertRaises(ValueError):
            self.g.enqueue('https://netkeiba.com.attacker.example/x',discovered_from='synthetic')
    def test_credentials_rejected(self):
        with self.assertRaises(ValueError):
            self.g.enqueue('https://a:b@netkeiba.com/x',discovered_from='synthetic')
    def test_duplicate_no_network(self):
        a=self.g.enqueue('https://race.netkeiba.com/x#part',discovered_from='synthetic')
        b=self.g.enqueue('https://race.netkeiba.com/x',discovered_from='synthetic')
        self.assertEqual(a,b); self.assertEqual(self.g.status()['total_reserved_requests'],0)
    def test_distinct_snapshots(self):
        a=self.g.enqueue('https://race.netkeiba.com/x',snapshot_key='before',discovered_from='synthetic')
        b=self.g.enqueue('https://race.netkeiba.com/x',snapshot_key='later',discovered_from='synthetic')
        self.assertNotEqual(a,b)
    def test_one_active(self):
        self.setup_task(); self.g.claim(self.now)
        self.assertEqual(self.g.claim(self.now)['state'],'IN_FLIGHT_OR_UNCERTAIN')
    def test_gap_from_response_completion(self):
        self.setup_task(); p=self.g.claim(self.now)
        self.finish(p,self.now+timedelta(seconds=30))
        self.assertEqual(self.g.claim(self.now+timedelta(seconds=149))['state'],'WAIT')
        self.assertEqual(self.g.claim(self.now+timedelta(seconds=150))['state'],'PERMIT')
    def test_five_then_one_hour(self):
        self.setup_task(6)
        for i in range(5):
            t=self.now+timedelta(seconds=120*i)
            p=self.g.claim(t); self.assertEqual(p['state'],'PERMIT'); self.finish(p,t)
        self.assertEqual(self.g.claim(self.now+timedelta(minutes=10))['state'],'WAIT')
        self.assertEqual(self.g.claim(self.now+timedelta(minutes=68))['state'],'PERMIT')
    def test_restart_preserves_wait(self):
        self.setup_task(); p=self.g.claim(self.now); self.finish(p)
        self.g.close(); self.g=Gate(self.path)
        self.assertEqual(self.g.claim(self.now+timedelta(seconds=1))['state'],'WAIT')
    def test_restart_preserves_uncertain(self):
        self.setup_task(); self.g.claim(self.now)
        self.g.close(); self.g=Gate(self.path)
        self.assertEqual(self.g.claim(self.now+timedelta(days=1))['state'],'IN_FLIGHT_OR_UNCERTAIN')
    def test_shared_process_database(self):
        self.setup_task()
        g2=Gate(self.path)
        try:
            self.g.claim(self.now)
            self.assertEqual(g2.claim(self.now)['state'],'IN_FLIGHT_OR_UNCERTAIN')
        finally:g2.close()
    def test_subdomains_share_gap(self):
        self.g.approve(self.now,'offline')
        self.g.enqueue('https://race.netkeiba.com/x',discovered_from='synthetic')
        self.g.enqueue('https://db.netkeiba.com/y',discovered_from='synthetic')
        p=self.g.claim(self.now); self.finish(p)
        self.assertEqual(self.g.claim(self.now+timedelta(seconds=1))['state'],'WAIT')
    def test_no_catchup_after_idle(self):
        self.setup_task(3)
        t=self.now+timedelta(days=7)
        p=self.g.claim(t);self.finish(p,t)
        self.assertEqual(self.g.claim(t+timedelta(seconds=1))['state'],'WAIT')
    def test_block_is_manual_pause(self):
        self.setup_task();p=self.g.claim(self.now);self.finish(p,outcome='blocked')
        self.assertEqual(self.g.claim(self.now+timedelta(days=2))['state'],'PAUSED')
    def test_retry_after_preserved_through_resume(self):
        self.setup_task();p=self.g.claim(self.now)
        self.finish(p,outcome='blocked',retry_after=self.now+timedelta(hours=2))
        self.g.resume(self.now+timedelta(minutes=1),'review complete, blocked task remains blocked')
        self.assertEqual(self.g.claim(self.now+timedelta(minutes=2))['state'],'WAIT')
    def test_timeout_counts_and_waits(self):
        self.setup_task(1);p=self.g.claim(self.now);self.finish(p,outcome='temporary')
        self.assertEqual(self.g.status()['total_reserved_requests'],1)
        self.assertEqual(self.g.claim(self.now+timedelta(hours=1))['state'],'NO_READY_TASK')
        self.assertEqual(self.g.claim(self.now+timedelta(hours=6))['state'],'PERMIT')
    def test_parse_failure_not_refetched(self):
        self.setup_task(1);p=self.g.claim(self.now);self.finish(p,outcome='parse_error')
        self.g.resume(self.now+timedelta(hours=2),'parser fixed; reparse local raw file')
        self.assertEqual(self.g.claim(self.now+timedelta(hours=2))['state'],'NO_READY_TASK')
        self.assertEqual(self.g.status()['tasks']['QUARANTINED'],1)
    def test_304_counted(self):
        self.setup_task();p=self.g.claim(self.now);self.finish(p,outcome='not_modified')
        self.assertEqual(self.g.status()['total_reserved_requests'],1)
    def test_not_found_no_retry(self):
        self.setup_task(1);p=self.g.claim(self.now);self.finish(p,outcome='not_found')
        self.assertEqual(self.g.status()['tasks']['NOT_FOUND'],1)
    def test_redirect_not_followed(self):
        self.setup_task(1);p=self.g.claim(self.now);self.finish(p,outcome='redirect')
        self.assertEqual(self.g.status()['tasks']['REDIRECT_REVIEW'],1)
    def test_priority_cannot_bypass(self):
        self.setup_task();p=self.g.claim(self.now);self.finish(p)
        self.g.enqueue('https://race.netkeiba.com/urgent',priority=999,discovered_from='synthetic')
        self.assertEqual(self.g.claim(self.now+timedelta(seconds=1))['state'],'WAIT')
    def test_night_window(self):
        self.setup_task()
        d=self.g.claim(self.now+timedelta(hours=15))
        self.assertEqual(d['state'],'OUTSIDE_WINDOW')
        self.assertEqual(datetime.fromtimestamp(d['next_at'],JST).hour,8)
    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):self.g.claim(datetime(2026,9,30,8))
    def test_backwards_clock_rejected(self):
        self.setup_task();self.g.claim(self.now)
        with self.assertRaises(ValueError):self.g.claim(self.now-timedelta(seconds=1))
    def test_config_change_does_not_reset(self):
        with self.assertRaises(ValueError):Gate(self.path,replace(Policy(),daily_requests=999))
    def test_finish_twice_rejected(self):
        self.setup_task();p=self.g.claim(self.now);self.finish(p)
        with self.assertRaises(ValueError):self.finish(p)
    def test_unfinished_requires_manual_abandon(self):
        self.setup_task();p=self.g.claim(self.now)
        with self.assertRaises(ValueError):self.g.resume(self.now,'cannot clear live request')
        self.finish(p,outcome='abandoned')
        self.assertEqual(self.g.claim(self.now+timedelta(hours=1))['state'],'PAUSED')
    def test_daily_and_rolling_limits(self):
        self.g.close()
        self.path=Path(self.tmp.name)/'small.sqlite'
        self.g=Gate(self.path,replace(Policy(),daily_requests=2,rolling24_requests=2))
        self.setup_task(4)
        for offset in (0,120):
            t=self.now+timedelta(seconds=offset);p=self.g.claim(t);self.finish(p,t)
        self.assertEqual(self.g.claim(self.now+timedelta(minutes=10))['state'],'DAILY_LIMIT')
        p=self.g.claim(self.now+timedelta(days=1));self.assertEqual(p['state'],'PERMIT')
        self.finish(p,self.now+timedelta(days=1,seconds=1))
        # At +24h+121s the prior second attempt is outside the rolling window.
        self.assertEqual(self.g.claim(self.now+timedelta(days=1,seconds=121))['state'],'PERMIT')
    def test_reserved_before_crash_consumes_budget(self):
        self.setup_task();self.g.claim(self.now)
        self.assertEqual(self.g.status()['total_reserved_requests'],1)

if __name__=='__main__':unittest.main()
