"""Timing utilities, not estimates of unobserved individual sectionals."""
from __future__ import annotations
import math
from typing import Sequence


def early_anchor(distance_m: float, finish_s: float, final600_s: float) -> dict:
    vals = (distance_m, finish_s, final600_s)
    if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals):
        raise ValueError('finite numeric observations required; missing is not zero')
    if distance_m <= 600 or not 0 < final600_s < finish_s:
        raise ValueError('inconsistent distance or timing')
    return {'distance_m': distance_m - 600,
            'elapsed_s': finish_s - final600_s,
            'kind': 'derived_from_finish_and_reported_final600',
            'is_direct_measurement': False}


def lap_endpoints(distance_m: int, *, verified_convention: str) -> list[int]:
    """Caller MUST have verified that the source uses this convention.

    The convention used here is first 100m for odd-hundred distances, then 200m.
    An unknown provider/convention must not be guessed from vector length.
    Prefer explicit endpoints supplied by the source.
    """
    if verified_convention != 'first100_if_odd_hundred_then200':
        raise ValueError('unverified timing convention')
    if not isinstance(distance_m, int) or isinstance(distance_m, bool) or distance_m <= 0 or distance_m % 100:
        raise ValueError('positive integral hundreds of metres required')
    first = 100 if distance_m % 200 else 200
    return list(range(first, distance_m + 1, 200))


def validate_laps(endpoints_m: Sequence[int], laps_s: Sequence[float], distance_m: int) -> None:
    if len(endpoints_m) != len(laps_s) or not laps_s:
        raise ValueError('explicit endpoints must match lap values')
    if endpoints_m[-1] != distance_m or endpoints_m[0] <= 0:
        raise ValueError('invalid first/last endpoint')
    if any(b <= a for a, b in zip(endpoints_m, endpoints_m[1:])):
        raise ValueError('endpoints must increase')
    if any(not isinstance(x, (int, float)) or not math.isfinite(x) or x <= 0 for x in laps_s):
        raise ValueError('lap values must be positive, finite, observed values')


def validate_lap_clock(endpoints_m, laps_s, fastest_finish_s, rounding_tolerance_s=0.3):
    """Tolerance is a configurable QA convention, not a precision claim."""
    validate_laps(endpoints_m, laps_s, endpoints_m[-1])
    if not math.isfinite(fastest_finish_s) or fastest_finish_s <= 0 or rounding_tolerance_s < 0:
        raise ValueError('invalid comparison values')
    return {'difference_s': sum(laps_s) - fastest_finish_s,
            'within_tolerance': abs(sum(laps_s) - fastest_finish_s) <= rounding_tolerance_s}
