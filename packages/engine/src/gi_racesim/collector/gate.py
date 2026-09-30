"""Persistent, fail-closed request gate and queue. Python 3.10+ standard library.

NO NETWORK CODE. A future adapter must claim exactly one permit per HTTP request
(including redirects/retries/robots) and finish it after saving the response.
All collectors must share this SQLite file. Separate copies do not coordinate.
Unfinished requests require manual abandonment after the worker is confirmed dead.
"""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone, time
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit, urlunsplit
import uuid

UTC = timezone.utc
JST = timezone(timedelta(hours=9))

@dataclass(frozen=True)
class Policy:
    group: str = 'netkeiba.com'
    min_gap_seconds: int = 120
    batch_requests: int = 5
    batch_rest_seconds: int = 3600
    daily_requests: int = 60
    rolling24_requests: int = 60
    open_hour_jst: int = 8
    close_hour_jst: int = 22
    max_attempts: int = 3

    def validate(self):
        for v in [self.min_gap_seconds, self.batch_requests,
                  self.batch_rest_seconds, self.daily_requests,
                  self.rolling24_requests, self.max_attempts]:
            if not isinstance(v, int) or isinstance(v, bool) or v < 1:
                raise ValueError('positive integer limits required')
        if not 0 <= self.open_hour_jst < self.close_hour_jst <= 24:
            raise ValueError('invalid daytime window')
        if not self.group or '.' not in self.group:
            raise ValueError('explicit source group required')


def stamp(now: datetime) -> float:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('timezone-aware datetime required')
    return now.timestamp()


def normalize_url(url: str, group: str) -> str:
    u = urlsplit(url)
    host = (u.hostname or '').lower()
    if u.scheme != 'https' or u.username or u.password or u.port not in (None, 443):
        raise ValueError('HTTPS without credentials/nonstandard port required')
    if host != group and not host.endswith('.' + group):
        raise ValueError('URL outside explicit source group')
    # Do NOT remove arbitrary query parameters: they may change the content.
    return urlunsplit(('https', host, u.path or '/', u.query, ''))


class Gate:
    def __init__(self, db_path: str | Path, policy: Policy | None = None):
        self.policy = policy or Policy()
        self.policy.validate()
        self.path = str(db_path)
        self.db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS control(
            id INTEGER PRIMARY KEY CHECK(id=1), policy_json TEXT NOT NULL,
            approved INTEGER NOT NULL DEFAULT 0, paused TEXT,
            next_at REAL NOT NULL DEFAULT 0, batch_used INTEGER NOT NULL DEFAULT 0,
            active_token TEXT, last_clock REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS task(
            id INTEGER PRIMARY KEY, url TEXT NOT NULL, snapshot_key TEXT NOT NULL,
            kind TEXT NOT NULL, priority INTEGER NOT NULL, discovered_from TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING', ready_at REAL NOT NULL DEFAULT 0,
            attempts INTEGER NOT NULL DEFAULT 0, last_outcome TEXT,
            UNIQUE(url,snapshot_key));
        CREATE TABLE IF NOT EXISTS attempt(
            token TEXT PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES task(id),
            started REAL NOT NULL, finished REAL, outcome TEXT, raw_ref TEXT);
        CREATE TABLE IF NOT EXISTS review(
            id INTEGER PRIMARY KEY, at REAL NOT NULL, action TEXT NOT NULL, note TEXT NOT NULL);
        ''')
        config = json.dumps(asdict(self.policy), sort_keys=True)
        with self.tx():
            r = self.db.execute('SELECT policy_json FROM control WHERE id=1').fetchone()
            if r is None:
                self.db.execute('INSERT INTO control(id,policy_json) VALUES(1,?)',(config,))
            elif r['policy_json'] != config:
                raise ValueError('policy differs from persisted policy; explicit migration required')

    def close(self):
        self.db.close()

    @contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def _clock(self, now: datetime):
        ts = stamp(now)
        r = self.db.execute('SELECT * FROM control WHERE id=1').fetchone()
        if ts < r['last_clock']:
            raise ValueError('clock moved backwards; collection must wait for review/time recovery')
        self.db.execute('UPDATE control SET last_clock=? WHERE id=1',(ts,))
        return ts, r

    def approve(self, now: datetime, note: str):
        """Record a human source review. This method does not establish permission."""
        if not note.strip():
            raise ValueError('review evidence/note required')
        with self.tx():
            ts, _ = self._clock(now)
            self.db.execute('UPDATE control SET approved=1 WHERE id=1')
            self.db.execute('INSERT INTO review(at,action,note) VALUES(?,?,?)',
                            (ts,'approve',note))

    def resume(self, now: datetime, note: str):
        if not note.strip():
            raise ValueError('review note required')
        with self.tx():
            ts, r = self._clock(now)
            if r['active_token']:
                raise ValueError('active or uncertain request: confirm worker stopped, then abandon')
            self.db.execute('UPDATE control SET paused=NULL WHERE id=1')
            self.db.execute('INSERT INTO review(at,action,note) VALUES(?,?,?)',
                            (ts,'resume_without_resetting_budget',note))

    def enqueue(self, url: str, *, snapshot_key='historical_v1', kind='result',
                priority=0, discovered_from: str, ready_at: datetime | None = None) -> int:
        url = normalize_url(url,self.policy.group)
        if not snapshot_key or not discovered_from:
            raise ValueError('snapshot key and discovery evidence required')
        ready = stamp(ready_at) if ready_at else 0.0
        with self.tx():
            self.db.execute('''INSERT OR IGNORE INTO task
                (url,snapshot_key,kind,priority,discovered_from,ready_at)
                VALUES(?,?,?,?,?,?)''',
                (url,snapshot_key,kind,int(priority),discovered_from,ready))
            return self.db.execute('SELECT id FROM task WHERE url=? AND snapshot_key=?',
                                   (url,snapshot_key)).fetchone()['id']

    def claim(self, now: datetime) -> dict:
        p = self.policy
        with self.tx():
            ts, r = self._clock(now)
            if not r['approved']:
                return {'state':'SOURCE_REVIEW_REQUIRED'}
            if r['paused']:
                return {'state':'PAUSED','reason':r['paused']}
            if r['active_token']:
                return {'state':'IN_FLIGHT_OR_UNCERTAIN'}
            local = now.astimezone(JST)
            day0 = datetime.combine(local.date(),time(0),JST).timestamp()
            if not p.open_hour_jst <= local.hour < p.close_hour_jst:
                next_day = local.date() if local.hour < p.open_hour_jst else local.date()+timedelta(days=1)
                when = datetime.combine(next_day,time(p.open_hour_jst),JST).timestamp()
                return {'state':'OUTSIDE_WINDOW','next_at':max(when,r['next_at'])}
            if ts < r['next_at']:
                return {'state':'WAIT','next_at':r['next_at']}
            day_used = self.db.execute('SELECT count(*) FROM attempt WHERE started>=?',(day0,)).fetchone()[0]
            if day_used >= p.daily_requests:
                return {'state':'DAILY_LIMIT','used':day_used}
            recent = self.db.execute('SELECT started FROM attempt WHERE started>? ORDER BY started',
                                     (ts-86400,)).fetchall()
            if len(recent) >= p.rolling24_requests:
                return {'state':'ROLLING24_LIMIT','next_at':recent[0]['started']+86400}
            t = self.db.execute('''SELECT * FROM task WHERE status='PENDING' AND ready_at<=?
                                   ORDER BY priority DESC,id LIMIT 1''',(ts,)).fetchone()
            if t is None:
                return {'state':'NO_READY_TASK'}
            token = uuid.uuid4().hex
            self.db.execute('UPDATE task SET status=\'IN_FLIGHT\',attempts=attempts+1 WHERE id=?',(t['id'],))
            self.db.execute('INSERT INTO attempt(token,task_id,started) VALUES(?,?,?)',(token,t['id'],ts))
            self.db.execute('UPDATE control SET active_token=?,batch_used=batch_used+1 WHERE id=1',(token,))
            return {'state':'PERMIT','token':token,'task_id':t['id'],'url':t['url'],
                    'snapshot_key':t['snapshot_key'],'kind':t['kind']}

    def finish(self, token: str, now: datetime, *, outcome: str, raw_ref: str | None=None,
               retry_after: datetime | None=None):
        """Outcomes classified by adapter. No automatic HTTP retry or redirect.

        ok/not_modified: saved content or cached revision is mandatory.
        blocked: 403/429/auth/challenge -> source-wide manual pause.
        temporary: timeout/5xx -> retry after 6h then 24h, max three attempts.
        parse_error: content saved but parser needs review; no re-fetch.
        not_found/redirect/abandoned: explicit, never silently succeed.
        """
        allowed={'ok','not_modified','blocked','temporary','parse_error','not_found','redirect','abandoned'}
        if outcome not in allowed:
            raise ValueError('unknown outcome')
        if outcome in {'ok','not_modified','parse_error'} and not raw_ref:
            raise ValueError('saved response/cache reference required')
        with self.tx():
            ts, r = self._clock(now)
            if r['active_token'] != token:
                raise ValueError('not the active request')
            a = self.db.execute('SELECT * FROM attempt WHERE token=?',(token,)).fetchone()
            if a is None or a['finished'] is not None or ts < a['started']:
                raise ValueError('invalid attempt completion')
            t = self.db.execute('SELECT * FROM task WHERE id=?',(a['task_id'],)).fetchone()
            end_batch = r['batch_used'] >= self.policy.batch_requests
            wait = self.policy.batch_rest_seconds if end_batch else self.policy.min_gap_seconds
            next_at = max(r['next_at'], ts + wait,
                          stamp(retry_after) if retry_after else 0.0)
            status='DONE'
            ready=ts
            paused=r['paused']
            if outcome in {'blocked','abandoned'}:
                status='BLOCKED' if outcome=='blocked' else 'UNCERTAIN'
                paused=outcome
            elif outcome=='temporary':
                if t['attempts'] >= self.policy.max_attempts:
                    status='FAILED'
                else:
                    status='PENDING'
                    hours=6 if t['attempts']==1 else 24
                    ready=max(ts+hours*3600,next_at)
                # A transport/server failure also slows unrelated pending requests.
                next_at=max(next_at, ts+self.policy.batch_rest_seconds)
            elif outcome=='parse_error':
                status='QUARANTINED'
                paused='parse_schema_review'
            elif outcome=='not_found':
                status='NOT_FOUND'
            elif outcome=='redirect':
                status='REDIRECT_REVIEW'
            self.db.execute('UPDATE attempt SET finished=?,outcome=?,raw_ref=? WHERE token=?',
                            (ts,outcome,raw_ref,token))
            self.db.execute('UPDATE task SET status=?,ready_at=?,last_outcome=? WHERE id=?',
                            (status,ready,outcome,t['id']))
            self.db.execute('''UPDATE control SET active_token=NULL,next_at=?,batch_used=?,paused=? WHERE id=1''',
                            (next_at,0 if end_batch else r['batch_used'],paused))

    def status(self) -> dict:
        control=dict(self.db.execute('SELECT * FROM control WHERE id=1').fetchone())
        control['tasks']={r['status']:r['n'] for r in self.db.execute('SELECT status,count(*) n FROM task GROUP BY status')}
        control['total_reserved_requests']=self.db.execute('SELECT count(*) FROM attempt').fetchone()[0]
        return control
