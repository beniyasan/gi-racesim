"""Parse a *verified* corner-notation dialect without inventing metric positions.

Dialect reference: netkeiba's own result-page legend, checked 2026-09-30.
Comma between groups = [1,2) lengths; '-' = [2,5); '=' = [5,infinity).
Inside parentheses comma separates inside-to-outside runners; it is NOT a gap.
An absent separator is deliberately left UNKNOWN. Unknown symbols are errors.
Only use this decoder for sources whose legend has been verified to match.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
import re
import unicodedata
from typing import Iterable

class NotationError(ValueError):
    """Keep the raw observation in quarantine; do not silently coerce it."""

@dataclass(frozen=True)
class Gap:
    symbol: str | None
    lower_lengths: float | None
    upper_lengths_exclusive: float | None
    category: str
    unit: str = 'horse_length_category_not_metres'

@dataclass(frozen=True)
class Group:
    members: tuple[int, ...]
    inner_to_outer: tuple[int, ...] | None
    marked_leader: int | None
    gap_from_previous: Gap | None
    within_group_longitudinal_span_lt_lengths: float | None

@dataclass(frozen=True)
class Corner:
    raw: str
    groups: tuple[Group, ...]
    dialect: str = 'netkeiba_legend_verified_2026-09-30'

    @property
    def horses(self) -> tuple[int, ...]:
        return tuple(h for g in self.groups for h in g.members)

    def to_dict(self) -> dict:
        return asdict(self)


def _gap(symbol: str | None) -> Gap:
    if symbol == ',':
        return Gap(symbol, 1.0, 2.0, 'one_to_under_two')
    if symbol == '-':
        return Gap(symbol, 2.0, 5.0, 'two_to_under_five')
    if symbol == '=':
        return Gap(symbol, 5.0, None, 'five_or_more')
    return Gap(None, None, None, 'unknown')


def parse_corner(text: str, expected_horses: Iterable[int] | None = None) -> Corner:
    """Parse syntax; a supplied expected roster is required to check completeness.

    Does not interpret HTML colour/bold, infer a finishing order, turn lengths into
    metres, or force a strict order inside a group. Missing records must be passed
    as missing by the caller, not as this function's empty string.
    """
    if not isinstance(text, str):
        raise NotationError('text must be a string')
    s = re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))
    if not s:
        raise NotationError('empty observation is missing, not an empty field')
    pos = 0
    seen: set[int] = set()
    groups: list[Group] = []
    previous_separator: str | None = None

    def horse() -> tuple[int, bool]:
        nonlocal pos
        star = pos < len(s) and s[pos] == '*'
        if star:
            pos += 1
        m = re.match(r'[0-9]+', s[pos:])
        if m is None:
            raise NotationError(f'horse number required at offset {pos}')
        n = int(m.group())
        pos += len(m.group())
        if n < 1 or n in seen:
            raise NotationError(f'invalid or duplicate runner {n}')
        seen.add(n)
        return n, star

    while pos < len(s):
        members: list[int] = []
        marked: list[int] = []
        in_group = s[pos] == '('
        if in_group:
            pos += 1
            while True:
                n, star = horse()
                members.append(n)
                if star:
                    marked.append(n)
                if pos >= len(s):
                    raise NotationError('unclosed group')
                if s[pos] == ')':
                    pos += 1
                    break
                if s[pos] != ',':
                    raise NotationError(f'invalid within-group separator at {pos}')
                pos += 1
        else:
            n, star = horse()
            members.append(n)
            if star:
                marked.append(n)
        if len(marked) > 1:
            raise NotationError('more than one marked leader in a group')
        groups.append(Group(
            members=tuple(members),
            inner_to_outer=tuple(members) if in_group else None,
            marked_leader=marked[0] if marked else None,
            gap_from_previous=None if not groups else _gap(previous_separator),
            within_group_longitudinal_span_lt_lengths=1.0 if in_group else None,
        ))
        if pos == len(s):
            break
        if s[pos] in ',-=':
            previous_separator = s[pos]
            pos += 1
            if pos == len(s):
                raise NotationError('trailing separator')
        elif s[pos] == '(' or s[pos].isdigit() or s[pos] == '*':
            # Adjacency is accepted, but its gap is not inferred.
            previous_separator = None
        else:
            raise NotationError(f'unknown symbol {s[pos]!r} at offset {pos}')

    if expected_horses is not None:
        exp = list(expected_horses)
        if len(exp) != len(set(exp)) or any(x < 1 for x in exp):
            raise NotationError('invalid expected roster')
        if seen != set(exp):
            raise NotationError(f'roster mismatch: missing={sorted(set(exp)-seen)}, unexpected={sorted(seen-set(exp))}')
    return Corner(text, tuple(groups))


def pair_observation(corner: Corner, a: int, b: int) -> dict:
    """Return only observable relations, never a fabricated total ordering.

    Explicit '*' is a source-reported leader, not a measured time difference.
    Numeric horse order must never become an arbitrary longitudinal tie-break.
    """
    if a == b or a not in corner.horses or b not in corner.horses:
        raise ValueError('two different observed runners are required')
    ia = next(i for i, g in enumerate(corner.groups) if a in g.members)
    ib = next(i for i, g in enumerate(corner.groups) if b in g.members)
    if ia != ib:
        return {'same_group': False, 'a_before_b': ia < ib,
                'a_inside_b': None, 'basis': 'ordered_groups'}
    g = corner.groups[ia]
    before = (True if g.marked_leader == a else
              False if g.marked_leader == b else None)
    inside = None if g.inner_to_outer is None else g.inner_to_outer.index(a) < g.inner_to_outer.index(b)
    return {'same_group': True, 'a_before_b': before, 'a_inside_b': inside,
            'basis': 'marked_leader' if before is not None else 'longitudinal_order_unknown'}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('notation')
    args = ap.parse_args()
    print(json.dumps(parse_corner(args.notation).to_dict(), ensure_ascii=False, indent=2))
