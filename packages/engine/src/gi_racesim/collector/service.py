"""Offline-first collector orchestration around the persistent request gate."""
from __future__ import annotations

from datetime import datetime, timezone
from html.parser import HTMLParser
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

from .cache import CacheStore
from .gate import Gate
from .transport import (
    DisabledTransport,
    ExternalAccessDisabled,
    HttpResponse,
    HttpTransport,
)


UTC = timezone.utc


def _wall_clock() -> datetime:
    return datetime.now(UTC)


class StructureChange(RuntimeError):
    """Parser signal that the source markup no longer matches its contract."""


def _ensure_time(value: datetime | None, now_fn: Callable[[], datetime]) -> datetime:
    value = now_fn() if value is None else value
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('timezone-aware datetime required')
    return value


def _blocked_reason(response: HttpResponse) -> str | None:
    """Return a non-sensitive reason for a source-wide access stop.

    A vendor name in a normal asset URL is not itself an access denial.  Body
    matching therefore only uses explicit challenge/interstitial signals; the
    raw body and header values are never returned in diagnostics.
    """
    if response.status_code in {401, 403, 407, 429}:
        return f'status_{response.status_code}'
    if 400 <= response.status_code <= 499 and response.status_code not in {404, 410}:
        return 'status_4xx'
    headers = response.headers
    for key, reason in (
        ('www-authenticate', 'authentication_header'),
        ('proxy-authenticate', 'proxy_authentication_header'),
        ('cf-mitigated', 'cloudflare_mitigated_header'),
        ('x-captcha', 'captcha_header'),
        ('x-challenge', 'challenge_header'),
    ):
        if key in headers:
            return reason
    sample = response.body[:256 * 1024].lower()
    # Keep ordinary references such as cdnjs.cloudflare.com out of this list.
    # These tokens identify challenge/interstitial markup rather than a vendor
    # name.  The existing captcha/access-denied markers remain conservative
    # source-wide stop signals.
    for marker, reason in (
        (b'captcha', 'captcha_marker'),
        (b'access denied', 'access_denied_marker'),
        (b'challenge-platform', 'challenge_platform_marker'),
        (b'cf-chl-', 'cloudflare_challenge_marker'),
        (b'cf-turnstile', 'cloudflare_turnstile_marker'),
        (b'cf-browser-verification', 'cloudflare_verification_marker'),
        (b'just a moment...', 'cloudflare_interstitial_marker'),
    ):
        if marker in sample:
            return reason
    return None


def _blocked_response(response: HttpResponse) -> bool:
    return _blocked_reason(response) is not None


def require_reviewed_source_structure(body: bytes) -> None:
    """Quarantine live HTML until WORK-006 establishes a reviewed source parser.

    html/body/table tags alone cannot distinguish result pages from a login or
    error page. Do not invent a source schema from the synthetic fixtures.
    The response is saved before this validator is called.
    """
    raise StructureChange('no reviewed source structure validator; review saved HTML in WORK-006')


class _SyntheticResultParser(HTMLParser):
    """A tiny declared fixture schema, never a real source-page heuristic."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.valid = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'table':
            self.tables.append({'th': set(), 'td': set()} if
                               attrs.get('data-giracesim') == 'synthetic-result-v1' else None)
        elif tag in {'th', 'td'} and self.tables and self.tables[-1] is not None:
            self.tables[-1][tag].add(attrs.get('data-field'))

    def handle_endtag(self, tag):
        if tag == 'table' and self.tables:
            table = self.tables.pop()
            if table is not None:
                required = {'horse', 'finish'}
                self.valid |= required <= table['th'] and required <= table['td']


def validate_synthetic_html_structure(body: bytes) -> None:
    """Validate only the explicitly labelled offline result-table fixture."""
    parser = _SyntheticResultParser()
    parser.feed(body.decode('utf-8'))
    parser.close()
    if not parser.valid:
        raise StructureChange('expected synthetic result table/columns are missing')


def classify_response(response: HttpResponse, requested_url: str) -> str:
    """Classify one response without issuing a follow-up request."""
    if _blocked_response(response):
        return 'blocked'
    if response.url and response.url != requested_url:
        return 'redirect'
    if response.status_code == 304:
        return 'not_modified'
    if 300 <= response.status_code <= 399:
        return 'redirect'
    if response.status_code in {404, 410}:
        return 'not_found'
    if 500 <= response.status_code <= 599 or response.status_code == 408:
        return 'temporary'
    if 200 <= response.status_code <= 299:
        return 'ok'
    if 400 <= response.status_code <= 499:
        # Unknown client errors are an access/source review signal.  They are
        # never silently treated as a successful page.
        return 'blocked'
    return 'temporary'


class Collector:
    """Coordinate one claim, at most one transport call, and one completion."""

    def __init__(self, gate: Gate, *, transport: HttpTransport | None = None,
                 cache: CacheStore | None = None,
                 response_parser: Callable[[bytes], Any] | None = None,
                 now_fn: Callable[[], datetime] | None = None):
        self.gate = gate
        self.transport = transport or DisabledTransport()
        if now_fn is not None and getattr(self.transport, 'live', True):
            raise ValueError('synthetic clock is not allowed with external transport')
        self.cache = cache or self._default_cache(gate)
        self.response_parser = response_parser
        if self.response_parser is None and getattr(self.transport, 'live', True):
            self.response_parser = require_reviewed_source_structure
        self.now_fn = now_fn or _wall_clock

    @staticmethod
    def _default_cache(gate: Gate) -> CacheStore:
        # The CLI supplies an explicit Application Support path.  This fallback
        # is only for library callers and remains adjacent to their chosen DB.
        if gate.path == ':memory:':
            return CacheStore(Path.cwd() / '.local' / 'collector-raw')
        return CacheStore(Path(gate.path).expanduser().with_suffix('.raw'))

    @staticmethod
    def _completion(start: datetime, now_fn: Callable[[], datetime]) -> datetime:
        candidate = _ensure_time(None, now_fn)
        if candidate.timestamp() < start.timestamp():
            raise ValueError('clock moved backwards during request; active token requires review')
        return candidate

    def tick(self, now: datetime | None = None) -> dict[str, Any]:
        """Run one conservative collection tick.

        The disabled check occurs before ``claim`` so the default command does
        not consume a request budget merely because live HTTP was not enabled.
        Once a permit is claimed, ``fetch`` appears exactly once in this method;
        no exception or status branch retries it or follows a redirect.
        """
        explicit_now = now is not None
        if explicit_now and getattr(self.transport, 'live', True):
            raise ValueError('synthetic timestamp is not allowed with external transport')
        start = _ensure_time(now, self.now_fn)
        if not getattr(self.transport, 'enabled', True):
            return {'state': 'EXTERNAL_DISABLED', 'transport_calls': 0}
        permit = self.gate.claim(start)
        if permit.get('state') != 'PERMIT':
            permit = dict(permit)
            permit['transport_calls'] = 0
            return permit
        token = permit['token']
        try:
            # This is the only transport invocation in the whole tick.
            response = self.transport.fetch(permit['url'])
        except ExternalAccessDisabled as error:
            # A transport may become disabled after claim (for example when an
            # operator changes configuration between processes).  It is still
            # a failed attempt and is handled without retrying.
            completion = start if explicit_now else self._completion(start, self.now_fn)
            self.gate.finish(token, completion, outcome='temporary')
            return {'state': 'TEMPORARY', 'outcome': 'temporary',
                    'token': token, 'error': str(error), 'transport_calls': 1}
        except Exception as error:
            completion = start if explicit_now else self._completion(start, self.now_fn)
            self.gate.finish(token, completion, outcome='temporary')
            return {'state': 'TEMPORARY', 'outcome': 'temporary',
                    'token': token, 'error': str(error) or error.__class__.__name__,
                    'transport_calls': 1}

        if not isinstance(response, HttpResponse):
            completion = start if explicit_now else self._completion(start, self.now_fn)
            self.gate.finish(token, completion, outcome='temporary')
            return {'state': 'TEMPORARY', 'outcome': 'temporary', 'token': token,
                    'error': 'transport returned an invalid response', 'transport_calls': 1}

        completion = start if explicit_now else self._completion(start, self.now_fn)
        try:
            entry = self.cache.save(token, response.body, {
                'requested_url': permit['url'],
                'response_url': response.url or permit['url'],
                'fetched_at': completion.isoformat(),
                'status_code': response.status_code,
                'headers': dict(response.headers),
                'snapshot_key': permit['snapshot_key'],
                'kind': permit['kind'],
            })
            self.gate.record_response(
                token, completion, raw_ref=entry.raw_ref, path=str(entry.path),
                status_code=response.status_code, headers=dict(response.headers),
                body_sha256=entry.body_sha256, body_bytes=entry.body_bytes,
                response_url=response.url or permit['url'])
        except Exception as error:
            # The saved file (if any) is preserved.  Keeping the active token
            # makes disk/metadata failures require explicit manual recovery,
            # rather than marking an unverified response as complete.
            return {'state': 'IN_FLIGHT_OR_UNCERTAIN', 'token': token,
                    'error': str(error) or error.__class__.__name__,
                    'transport_calls': 1}

        block_reason = _blocked_reason(response)
        outcome = 'blocked' if block_reason is not None else classify_response(response, permit['url'])
        if outcome == 'ok' and self.response_parser is not None:
            try:
                parser_result = self.response_parser(response.body)
                if parser_result is False:
                    raise StructureChange('response parser rejected source structure')
            except Exception as error:
                # A parser failure is a source/schema review signal.  The
                # response is already saved, so finish it as quarantined and
                # never fetch the same task automatically.
                outcome = 'parse_error'
                parser_error = str(error) or error.__class__.__name__
            else:
                parser_error = None
        else:
            parser_error = None
        self.gate.finish(token, completion, outcome=outcome, raw_ref=entry.raw_ref)
        result = {
            'state': outcome.upper(),
            'outcome': outcome,
            'token': token,
            'task_id': permit['task_id'],
            'url': permit['url'],
            'raw_ref': entry.raw_ref,
            'status_code': response.status_code,
            'transport_calls': 1,
        }
        if parser_error is not None:
            result['error'] = parser_error
        if block_reason is not None:
            result['block_reason'] = block_reason
        return result

    def status(self) -> dict[str, Any]:
        return self.gate.status()

    def pause(self, now: datetime, note: str) -> None:
        self.gate.pause(now, note)

    def resume(self, now: datetime, note: str) -> None:
        self.gate.resume(now, note)

    def abandon(self, token: str, now: datetime, note: str) -> None:
        self.gate.abandon(token, now, note)

    def approve(self, now: datetime, note: str) -> None:
        self.gate.approve(now, note)

    def enqueue(self, url: str, *, snapshot_key: str = 'historical_v1',
                kind: str = 'result', priority: int = 0,
                discovered_from: str, ready_at: datetime | None = None) -> int:
        return self.gate.enqueue(url, snapshot_key=snapshot_key, kind=kind,
                                 priority=priority, discovered_from=discovered_from,
                                 ready_at=ready_at)

    def parse_cache(self, raw_ref: str | None = None, *, adapter: str = 'generic') -> list[dict[str, Any]]:
        """Parse saved HTML locally; no gate claim and no transport call.

        ``netkeiba-shutuba`` is deliberately an offline adapter. It only
        consumes a response already recorded in the ledger and verifies the
        saved bytes before extracting the reviewed entry-table shape.
        """
        responses = self.gate.responses(raw_ref)
        if adapter == 'generic':
            return [self.cache.parse(response) for response in responses]
        if adapter != 'netkeiba-shutuba':
            raise ValueError(f'unknown cache adapter: {adapter}')
        from gi_racesim.normalization.netkeiba_shutuba import (
            ShutubaStructureError,
            parse_shutuba_html,
        )
        results: list[dict[str, Any]] = []
        for response in responses:
            result: dict[str, Any] = {
                'raw_ref': response['raw_ref'],
                'path': response['path'],
                'status_code': response.get('status_code'),
            }
            try:
                body = Path(str(response['path'])).read_bytes()
                digest = sha256(body).hexdigest()
                if digest != response.get('body_sha256'):
                    result.update({'state': 'HASH_MISMATCH', 'body_sha256': digest,
                                   'body_bytes': len(body)})
                elif response.get('status_code', 0) < 200 or response.get('status_code', 0) >= 300:
                    result.update({'state': 'NOT_PARSEABLE', 'body_sha256': digest,
                                   'body_bytes': len(body), 'error': 'response is not a 2xx page'})
                else:
                    normalized = parse_shutuba_html(
                        body,
                        source_url=str(response['requested_url']),
                    )
                    normalized['source'].update({
                        'raw_ref': response['raw_ref'],
                        'requested_url': response['requested_url'],
                        'response_url': response.get('response_url'),
                        'fetched_at': response.get('fetched'),
                        'status_code': response.get('status_code'),
                    })
                    result.update({'state': 'PARSED', 'normalized': normalized})
            except (OSError, ShutubaStructureError, UnicodeError, ValueError) as error:
                result.update({'state': 'PARSE_ERROR', 'error': str(error) or error.__class__.__name__})
            results.append(result)
        return results
