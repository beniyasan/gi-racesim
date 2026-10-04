"""Parser for the reviewed netkeiba pre-race entry-table structure.

The parser consumes saved UTF-8 bytes only.  It does not fetch linked horse,
jockey, trainer, odds, or prediction pages.  A source review must establish
that the markup still matches this adapter before it is connected to live
collection.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
import hashlib
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit


JST = timezone(timedelta(hours=9))
SOURCE_HOST = 'race.netkeiba.com'
SOURCE_PATH = '/race/shutuba.html'


class ShutubaStructureError(ValueError):
    """The saved page is not the reviewed entry-table shape."""


def _text(value: str) -> str:
    return ' '.join(value.split())


def _number(value: str, *, field: str) -> int:
    normalized = _text(value)
    if re.fullmatch(r'\d+', normalized) is None:
        raise ShutubaStructureError(f'{field} is missing')
    return int(normalized)


def _weight(value: str) -> float | None:
    value = _text(value)
    if not value or value in {'---.-', '--'}:
        return None
    if re.fullmatch(r'\d+(?:\.\d+)?', value) is None:
        raise ShutubaStructureError(f'invalid numeric weight: {value!r}')
    return float(value)


@dataclass
class _Cell:
    classes: str
    text: str = ''
    hrefs: list[str] | None = None

    def __post_init__(self) -> None:
        if self.hrefs is None:
            self.hrefs = []


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ''
        self.race_name = ''
        self.race_data01 = ''
        self.race_data02_spans: list[str] = []
        self._context: list[str] = []
        self._context_tags: list[str] = []
        self._context_text: dict[str, list[str]] = {}
        self._table_depth = 0
        self._entry_table = False
        self.entry_table_count = 0
        self.header_classes: list[str] = []
        self._header_row = False
        self._row: dict[str, Any] | None = None
        self._cell: _Cell | None = None
        self._link: str | None = None
        self.rows: list[dict[str, Any]] = []

    @staticmethod
    def _has_class(classes: str, name: str) -> bool:
        return name in classes.split()

    def _begin_context(self, name: str, tag: str) -> None:
        self._context.append(name)
        self._context_tags.append(tag)
        self._context_text.setdefault(name, [])

    def _end_context(self, tag: str) -> None:
        for index in range(len(self._context_tags) - 1, -1, -1):
            if self._context_tags[index] == tag:
                self._context.pop(index)
                self._context_tags.pop(index)
                return

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = attrs_dict.get('class') or ''
        if tag == 'title':
            self._begin_context('title', tag)
        if tag in {'h1', 'div'} and self._has_class(classes, 'RaceName'):
            self._begin_context('race_name', tag)
        if tag == 'div' and self._has_class(classes, 'RaceData01'):
            self._begin_context('race_data01', tag)
        if tag == 'div' and self._has_class(classes, 'RaceData02'):
            self._begin_context('race_data02', tag)
        if tag == 'span' and 'race_data02' in self._context:
            self._begin_context('race_data02_span', tag)

        if tag == 'table' and self._has_class(classes, 'ShutubaTable'):
            if not self._entry_table and 'PredictRap_Table' not in classes:
                self._entry_table = True
                self._table_depth = 1
                self.entry_table_count += 1
            elif self._entry_table:
                self._table_depth += 1
        elif self._entry_table:
            if tag == 'table':
                self._table_depth += 1
            if tag == 'tr' and self._has_class(classes, 'HorseList'):
                self._row = {'cells': []}
                self._cell = None
            elif tag == 'tr' and self._has_class(classes, 'Header'):
                self._header_row = True
            elif self._header_row and tag == 'th':
                self.header_classes.append(classes)
            elif self._row is not None and tag == 'td':
                self._cell = _Cell(classes)
                self._row['cells'].append(self._cell)
            elif self._cell is not None and tag == 'a':
                self._link = attrs_dict.get('href')

    def handle_endtag(self, tag: str) -> None:
        if self._entry_table:
            if tag == 'td':
                self._cell = None
                self._link = None
            elif tag == 'tr' and self._row is not None:
                self.rows.append(self._row)
                self._row = None
            elif tag == 'tr' and self._header_row:
                self._header_row = False
            elif tag == 'table':
                self._table_depth -= 1
                if self._table_depth <= 0:
                    self._entry_table = False
        self._end_context(tag)

    def handle_data(self, data: str) -> None:
        if not data:
            return
        for context in self._context:
            self._context_text.setdefault(context, []).append(data)
        if self._context:
            if 'race_data02_span' in self._context and data.strip():
                self.race_data02_spans.append(_text(data))
        if self._cell is not None:
            self._cell.text += data
            if self._link and self._link not in (self._cell.hrefs or []):
                self._cell.hrefs.append(self._link)

    def close(self) -> None:
        super().close()
        self.title = _text(' '.join(self._context_text.get('title', [])))
        self.race_name = _text(' '.join(self._context_text.get('race_name', [])))
        self.race_data01 = _text(' '.join(self._context_text.get('race_data01', [])))


def _cell(row: dict[str, Any], prefix: str) -> _Cell:
    for cell in row['cells']:
        tokens = cell.classes.split()
        if any(token.startswith(prefix) for token in tokens) if prefix in {'Waku', 'Umaban'} else prefix in tokens:
            return cell
    raise ShutubaStructureError(f'entry cell {prefix} is missing')


def _parse_entry(row: dict[str, Any]) -> dict[str, Any]:
    cells: list[_Cell] = row['cells']
    frame = _number(_cell(row, 'Waku').text, field='frame_no')
    gate = _number(_cell(row, 'Umaban').text, field='gate_no')
    horse_cell = _cell(row, 'HorseInfo')
    horse_name = _text(horse_cell.text)
    horse_id = None
    for href in horse_cell.hrefs or []:
        parsed_href = urlsplit(href)
        match = re.fullmatch(r'/horse/(\d+)', parsed_href.path)
        if parsed_href.scheme != 'https' or parsed_href.hostname != 'db.netkeiba.com':
            match = None
        if match:
            horse_id = match.group(1)
            break
    if not horse_id or not horse_name:
        raise ShutubaStructureError('horse ID/name is missing')
    barei_cell = _cell(row, 'Barei')
    barei = _text(barei_cell.text)
    barei_index = next(i for i, cell in enumerate(cells) if cell is barei_cell)
    if barei_index + 1 >= len(cells):
        raise ShutubaStructureError('carried weight is missing')
    carried_kg = _weight(cells[barei_index + 1].text)
    jockey = _text(_cell(row, 'Jockey').text)
    trainer = _text(_cell(row, 'Trainer').text)
    weight = _weight(_cell(row, 'Weight').text)
    return {
        'horse_id': horse_id,
        'gate_no': gate,
        'frame_no': frame,
        'name': horse_name,
        'sex_age': barei,
        'carried_kg': carried_kg,
        'jockey': jockey,
        'trainer': trainer,
        'body_weight_kg': weight,
    }


def parse_shutuba_html(body: bytes, *, source_url: str | None = None,
                       expected_race_id: str | None = None) -> dict[str, Any]:
    """Parse a saved netkeiba entry page into a source-specific record."""
    if not isinstance(body, bytes) or not body:
        raise ShutubaStructureError('non-empty UTF-8 HTML bytes required')
    try:
        text = body.decode('utf-8')
    except UnicodeDecodeError as exc:
        raise ShutubaStructureError('source HTML must be UTF-8') from exc
    markers = re.findall(r"_shutuba_race_id\s*=\s*['\"](\d{12})['\"]", text)
    if len(set(markers)) != 1:
        raise ShutubaStructureError('exactly one consistent _shutuba_race_id marker is required')
    race_id = markers[0]
    if not race_id:
        raise ShutubaStructureError('race_id marker is missing')
    if expected_race_id is not None and race_id != expected_race_id:
        raise ShutubaStructureError('race_id does not match requested task')
    if source_url is not None:
        parsed_url = urlsplit(source_url)
        if parsed_url.scheme != 'https' or parsed_url.hostname != SOURCE_HOST or parsed_url.path != SOURCE_PATH:
            raise ShutubaStructureError('source URL is outside the reviewed shutuba endpoint')
        url_race_ids = parse_qs(parsed_url.query, keep_blank_values=True).get('race_id', [])
        if len(url_race_ids) != 1 or url_race_ids[0] != race_id:
            raise ShutubaStructureError('source URL race_id does not match page marker')

    parser = _PageParser()
    parser.feed(text)
    parser.close()
    if parser.entry_table_count != 1 or not parser.rows:
        raise ShutubaStructureError('reviewed ShutubaTable rows are missing')
    required_headers = {'Waku', 'Umaban', 'HorseInfo', 'Barei', 'Jockey', 'Trainer'}
    header_tokens = {classes.split()[0] for classes in parser.header_classes if classes.split()}
    if not required_headers <= header_tokens:
        raise ShutubaStructureError('reviewed entry-table headers are missing')
    if not parser.race_name or not parser.race_data01:
        raise ShutubaStructureError('race metadata is missing')
    start_match = re.search(r'(\d{1,2}:\d{2})発走\s*/\s*(芝|ダート|ダ)\s*(\d+)m', parser.race_data01)
    date_match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', parser.title)
    if not start_match or not date_match:
        raise ShutubaStructureError('race start date/time or surface/distance is missing')
    year, month, day = (int(value) for value in date_match.groups())
    hour, minute = (int(value) for value in start_match.group(1).split(':'))
    start_at = datetime(year, month, day, hour, minute, tzinfo=JST).isoformat(timespec='seconds')
    surface = 'turf' if start_match.group(2) == '芝' else 'dirt'
    distance_m = int(start_match.group(3))
    course = next((value for value in parser.race_data02_spans if value and not re.fullmatch(r'\d+回|\d+日目|\d+頭', value)), None)
    field_size = next((int(re.match(r'(\d+)', value).group(1)) for value in parser.race_data02_spans
                       if re.fullmatch(r'\d+頭', value)), None)
    if not course or field_size is None:
        raise ShutubaStructureError('course or field size is missing')
    entries = [_parse_entry(row) for row in parser.rows]
    gates = [entry['gate_no'] for entry in entries]
    horses = [entry['horse_id'] for entry in entries]
    if len(gates) != len(set(gates)) or len(horses) != len(set(horses)):
        raise ShutubaStructureError('duplicate gate or horse ID')
    if field_size != len(entries):
        raise ShutubaStructureError('declared field size differs from entry rows')
    return {
        'source': {
            'adapter': 'netkeiba_shutuba_v1',
            'source_url': source_url,
            'raw_sha256': hashlib.sha256(body).hexdigest(),
            'raw_bytes': len(body),
        },
        'race': {
            'race_id': race_id,
            'name': parser.race_name,
            'course': course,
            'surface': surface,
            'distance_m': distance_m,
            'start_at': start_at,
            'field_size': field_size,
        },
        'entries': entries,
        'quality': {
            'missing_fields': ['results', 'laps', 'corners', 'odds_at_start'],
            'notes': [
                'This is a pre-race entry page; no result or measured race observation is inferred.',
                'Linked pages are not fetched by this adapter.',
            ],
        },
    }
