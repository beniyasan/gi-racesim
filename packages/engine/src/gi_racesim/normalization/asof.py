"""Separate prospective information availability from historical reconstruction."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any


def _time(value: str | datetime) -> datetime:
    t = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(t, datetime) or t.tzinfo is None or t.utcoffset() is None:
        raise ValueError('timezone-aware timestamps required')
    return t.astimezone(timezone.utc)


def eligible_history(record: dict[str, Any], *, target_start: str, as_of: str, mode: str) -> bool:
    """Event-time filtering is not evidence that the data were held in the past.

    Strict mode requires known publication AND collection times. Reconstruction
    is allowed for previous race outcomes, but MUST be labelled retrospective.
    This function does not authorize current lifetime-statistics as past inputs.
    """
    cut = _time(as_of)
    target = _time(target_start)
    if cut >= target:
        raise ValueError('as_of must precede the target start')
    if _time(record['event_at']) >= cut:
        return False
    if record.get('record_kind') != 'historical_race_result':
        return False
    if mode == 'retrospective':
        return True
    if mode != 'prospective':
        raise ValueError('mode must be prospective or retrospective')
    if not record.get('available_at') or not record.get('collected_at'):
        return False
    return _time(record['available_at']) <= cut and _time(record['collected_at']) <= cut
