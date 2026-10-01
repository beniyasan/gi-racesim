"""Command line entry point for the offline-first collector."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from .cache import CacheStore
from .gate import Gate, JST, Policy
from .service import Collector, require_reviewed_source_structure, validate_synthetic_html_structure
from .transport import DisabledTransport, HttpResponse, MockTransport, UrllibTransport


DEFAULT_STATE_DIR = Path.home() / 'Library' / 'Application Support' / 'GIRaceSim'


def parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value[:-1] + '+00:00' if value.endswith('Z') else value
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise argparse.ArgumentTypeError('invalid ISO-8601 timestamp') from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise argparse.ArgumentTypeError('timestamp must include a timezone')
    return result


def _common_options(parser: argparse.ArgumentParser) -> None:
    # ``SUPPRESS`` allows the same options before or after the subcommand
    # without a subparser default overwriting the global value.
    parser.add_argument('--db', type=Path, default=argparse.SUPPRESS,
                        help='SQLite request ledger path')
    parser.add_argument('--cache-dir', type=Path, default=argparse.SUPPRESS,
                        help='directory for immutable response HTML')
    parser.add_argument('--source-group', default=argparse.SUPPRESS,
                        help='one shared HTTPS source group (default: netkeiba.com)')
    parser.add_argument('--now', type=parse_time, default=argparse.SUPPRESS,
                        help='timezone-aware timestamp, useful for deterministic checks')


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='gi-racesim-collector')
    parser.add_argument('--db', type=Path, default=DEFAULT_STATE_DIR / 'collector.sqlite3',
                        help='SQLite request ledger path')
    parser.add_argument('--cache-dir', type=Path, default=DEFAULT_STATE_DIR / 'raw',
                        help='directory for immutable response HTML')
    parser.add_argument('--source-group', default='netkeiba.com',
                        help='one shared HTTPS source group')
    parser.add_argument('--now', type=parse_time, default=None,
                        help='timezone-aware timestamp, useful for deterministic checks')
    sub = parser.add_subparsers(dest='command', required=True)

    status = sub.add_parser('status', help='show persistent gate and cache status')
    _common_options(status)

    approve = sub.add_parser('approve', help='record human source review')
    _common_options(approve)
    approve.add_argument('--note', required=True)

    enqueue = sub.add_parser('enqueue', help='add one URL to the shared ledger')
    _common_options(enqueue)
    enqueue.add_argument('url')
    enqueue.add_argument('--snapshot-key', default='historical_v1')
    enqueue.add_argument('--kind', default='result')
    enqueue.add_argument('--priority', type=int, default=0)
    enqueue.add_argument('--discovered-from', required=True)
    enqueue.add_argument('--ready-at', type=parse_time)

    tick = sub.add_parser('tick', help='claim and process at most one response')
    _common_options(tick)
    mode = tick.add_mutually_exclusive_group()
    mode.add_argument('--allow-external', action='store_true',
                      help='explicitly opt into the no-retry/no-redirect urllib transport')
    mode.add_argument('--mock-html', '--mock-response', dest='mock_html', type=Path,
                      help='read one local HTML body and use a mock response')
    tick.add_argument('--mock-status', type=int, default=200)
    tick.add_argument('--mock-url', help='response URL for mock redirect checks')

    pause = sub.add_parser('pause', help='pause the source group without resetting budgets')
    _common_options(pause)
    pause.add_argument('--note', required=True)

    resume = sub.add_parser('resume', help='resume after manual review')
    _common_options(resume)
    resume.add_argument('--note', required=True)

    abandon = sub.add_parser('abandon', help='mark an uncertain active request abandoned')
    _common_options(abandon)
    abandon.add_argument('--token', required=True)
    abandon.add_argument('--note', required=True)

    parse_cache = sub.add_parser('parse-cache', help='parse saved HTML without any HTTP')
    _common_options(parse_cache)
    parse_cache.add_argument('--ref', help='one cache reference; otherwise parse all saved responses')
    return parser


def _transport(args: argparse.Namespace):
    if args.command != 'tick':
        return DisabledTransport()
    if args.mock_html is not None:
        body = args.mock_html.read_bytes()
        response = HttpResponse(args.mock_status, body, {}, args.mock_url)
        return MockTransport(response)
    if args.allow_external:
        return UrllibTransport(allow_external=True)
    return DisabledTransport()


def _timestamp(args: argparse.Namespace) -> datetime:
    return args.now or datetime.now(JST)


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f'not JSON serializable: {type(value).__name__}')


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == 'tick' and args.allow_external and args.now is not None:
        parser.error('--now cannot be used with --allow-external; live ticks use wall clock time')
    db_path: Path = args.db.expanduser()
    cache_dir: Path = args.cache_dir.expanduser()
    gate = None
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        cache_dir.mkdir(parents=True, exist_ok=True)
        gate = Gate(db_path, Policy(group=args.source_group))
        # A synthetic structure contract must never validate live source HTML.
        response_parser = (validate_synthetic_html_structure
                           if args.command == 'tick' and args.mock_html is not None
                           else require_reviewed_source_structure)
        collector = Collector(gate, transport=_transport(args), cache=CacheStore(cache_dir),
                              response_parser=response_parser)
        if args.command == 'status':
            result = collector.status()
        elif args.command == 'approve':
            collector.approve(_timestamp(args), args.note)
            result = collector.status()
        elif args.command == 'enqueue':
            task_id = collector.enqueue(
                args.url, snapshot_key=args.snapshot_key, kind=args.kind,
                priority=args.priority, discovered_from=args.discovered_from,
                ready_at=args.ready_at)
            result = {'state': 'ENQUEUED', 'task_id': task_id}
        elif args.command == 'tick':
            result = collector.tick(args.now)
        elif args.command == 'pause':
            collector.pause(_timestamp(args), args.note)
            result = collector.status()
        elif args.command == 'resume':
            collector.resume(_timestamp(args), args.note)
            result = collector.status()
        elif args.command == 'abandon':
            collector.abandon(args.token, _timestamp(args), args.note)
            result = collector.status()
        elif args.command == 'parse-cache':
            result = {'state': 'PARSED_CACHE', 'entries': collector.parse_cache(args.ref)}
        else:  # pragma: no cover - argparse enforces the set above
            parser.error(f'unknown command: {args.command}')
            return 2
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'state': 'ERROR', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if gate is not None:
            gate.close()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=_json_default))
    return 0


if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
