"""Viewer contract validation against the shared schema plus domain invariants.

The schema uses a documented small JSON Schema subset (see contracts README).
This is not a general-purpose JSON Schema validator. It never resolves remote
references and has no network dependencies.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
import hashlib
from importlib.resources import files
import json
import math
from pathlib import Path
import re
from typing import Any

MAX_BYTES = 5 * 1024 * 1024


class ContractError(ValueError):
    """The result cannot be imported without losing its meaning."""


@lru_cache(maxsize=1)
def _schema() -> dict:
    # The package build copies the authoritative contracts/ schema as a resource.
    return json.loads(files('gi_racesim.common').joinpath('viewer-schema.json').read_text())


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def _type(value: Any, kind: str) -> bool:
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    return {
        'null': value is None,
        'boolean': isinstance(value, bool),
        'object': isinstance(value, dict),
        'array': isinstance(value, list),
        'string': isinstance(value, str),
        'number': numeric,
        'integer': numeric and value == int(value),
    }[kind]


def _check(value: Any, schema: dict, root: dict, path: str = '$') -> None:
    if '$ref' in schema:
        name = schema['$ref'].removeprefix('#/$defs/')
        _check(value, root['$defs'][name], root, path)
        return
    if 'anyOf' in schema:
        for option in schema['anyOf']:
            try:
                _check(value, option, root, path)
                return
            except ContractError:
                pass
        raise ContractError(f'{path}: does not match any allowed shape')
    if 'const' in schema:
        _require(value == schema['const'], f'{path}: unsupported constant')
    if 'enum' in schema:
        _require(any(type(value) is type(item) and value == item for item in schema['enum']), f'{path}: invalid enum')
    if 'type' in schema:
        kinds = schema['type'] if isinstance(schema['type'], list) else [schema['type']]
        _require(any(_type(value, kind) for kind in kinds), f'{path}: invalid type')
    if isinstance(value, dict):
        props = schema.get('properties', {})
        _require(set(schema.get('required', [])) <= value.keys(), f'{path}: missing field')
        if schema.get('additionalProperties') is False:
            _require(value.keys() <= props.keys(), f'{path}: unknown field')
        for key in value.keys() & props.keys():
            _check(value[key], props[key], root, f'{path}.{key}')
    elif isinstance(value, list):
        _require(schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', math.inf), f'{path}: invalid length')
        for index, item in enumerate(value):
            _check(item, schema['items'], root, f'{path}[{index}]')
    elif isinstance(value, str):
        _require(schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', math.inf), f'{path}: invalid length')
        if 'pattern' in schema:
            _require(re.search(schema['pattern'], value) is not None, f'{path}: invalid string')
        if schema.get('format') == 'date-time':
            try:
                parsed = _timestamp(value)
                _require(parsed.tzinfo is not None, f'{path}: timezone required')
            except ValueError as exc:
                raise ContractError(f'{path}: invalid timestamp') from exc
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        _require(math.isfinite(value), f'{path}: finite number required')
        _require(schema.get('minimum', -math.inf) <= value <= schema.get('maximum', math.inf), f'{path}: out of bounds')
        if 'exclusiveMinimum' in schema:
            _require(value > schema['exclusiveMinimum'], f'{path}: must be positive')


def _unique(values: list, message: str) -> None:
    _require(len(values) == len(set(values)), message)


def _laps(lap: dict, distance: int) -> None:
    ends = lap['segment_ends_m']
    _require(len(ends) == len(lap['values_s']), 'lap lengths differ')
    _require(all(a < b for a, b in zip(ends, ends[1:])), 'lap endpoints must increase')
    _require(ends[-1] == distance, 'lap endpoints must cover race distance; use null for missing values')


def _corners(corners: list, roster: set[int]) -> None:
    _unique([c['checkpoint'] for c in corners], 'duplicate checkpoint')
    for corner in corners:
        accounted = list(corner['unobserved_gate_numbers'])
        if accounted:
            _require(corner['unknown_reason'] is not None, 'missing runners need an explanation')
        for index, group in enumerate(corner['groups']):
            members = group['members']
            accounted.extend(members)
            order = group['inner_to_outer']
            if order is not None:
                _require(len(order) == len(members) and set(order) == set(members), 'inner order must be a permutation of members')
            _require(group['marked_leader'] is None or group['marked_leader'] in members, 'leader outside group')
            _require((group['gap_from_previous'] is None) == (index == 0), 'only first group has no preceding gap')
        _unique(accounted, 'runner appears twice at a checkpoint')
        _require(set(accounted) == roster, 'checkpoint must account for roster with observed or unknown runners')


def validate_bundle(bundle: Any) -> dict:
    schema = _schema()
    _check(bundle, schema, schema)
    race, sim = bundle['race'], bundle['simulation']
    _unique([r['gate_no'] for r in race['runners']], 'duplicate gate number')
    _unique([r['horse_id'] for r in race['runners']], 'duplicate horse id')
    _require(_timestamp(bundle['as_of']) < _timestamp(race['start_at']), 'as_of must precede start')
    _require(_timestamp(bundle['generated_at']) >= _timestamp(bundle['as_of']), 'generation predates inputs')
    if bundle['mode'] == 'prospective':
        _require(_timestamp(bundle['generated_at']) < _timestamp(race['start_at']), 'prospective result must be generated before start')
    if bundle['origin'] != 'synthetic':
        _require(bundle['model_id'] is not None, 'prediction needs a model version')
        _require(bundle['producer_code_commit'] != '0' * 40, 'prediction needs a code commit')
    _require(sim['completed_trials'] <= sim['total_trials'], 'completed trials exceed attempts')
    _require(len(sim['representative_trials']) <= sim['completed_trials'], 'representatives exceed completed trials')
    _unique([t['trial_id'] for t in sim['representative_trials']], 'duplicate representative trial')
    roster = {r['gate_no'] for r in race['runners']}
    for trial in sim['representative_trials']:
        _laps(trial['laps'], race['distance_m'])
        _corners(trial['corners'], roster)
    quantiles = sim['lap_quantiles']
    ends = [q['segment_end_m'] for q in quantiles]
    _require(all(a < b for a, b in zip(ends, ends[1:])), 'aggregate endpoints must increase')
    if ends:
        _require(ends[-1] == race['distance_m'], 'aggregate endpoints must cover distance')
    for q in quantiles:
        values = [q['p10_s'], q['p50_s'], q['p90_s']]
        _require(q['sample_count'] <= sim['completed_trials'], 'aggregate sample exceeds completed trials')
        if q['sample_count'] == 0:
            _require(all(v is None for v in values), 'unobserved quantiles must be null')
        else:
            _require(all(v is not None for v in values), 'observed quantiles must be numeric')
            _require(values == sorted(values), 'quantiles out of order')
    observations = bundle['observations']
    if observations['laps'] is not None:
        _laps(observations['laps'], race['distance_m'])
    _corners(observations['corners'], roster)
    return bundle


def canonical_json(bundle: dict) -> str:
    validate_bundle(bundle)
    return json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def bundle_sha256(bundle: dict) -> str:
    """Python export identity. Importers compare the SHA-256 of the actual bytes."""
    return hashlib.sha256((canonical_json(bundle) + '\n').encode('utf-8')).hexdigest()


def read_bundle(path: str | Path) -> dict:
    with Path(path).open('rb') as handle:
        payload = handle.read(MAX_BYTES + 1)
    _require(len(payload) <= MAX_BYTES, 'bundle exceeds 5 MiB')
    try:
        return validate_bundle(json.loads(payload.decode('utf-8')))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError('invalid UTF-8 JSON') from exc
