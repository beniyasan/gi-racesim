"""Do not confuse changing group indices with actual positional progress."""
from __future__ import annotations
from .corners import Corner


def rank_band(corner: Corner, horse: int, *, declared_roster: list[int]) -> dict:
    roster=set(declared_roster)
    if len(roster)!=len(declared_roster) or horse not in corner.horses:
        raise ValueError('unique declared roster and observed target required')
    if not set(corner.horses).issubset(roster):
        raise ValueError('unexpected runner')
    missing=len(roster-set(corner.horses))
    ahead=0
    for group in corner.groups:
        if horse not in group.members:
            ahead+=len(group.members)
            continue
        if group.marked_leader==horse or len(group.members)==1:
            low=high=ahead+1
        else:
            low=ahead+(2 if group.marked_leader is not None else 1)
            high=ahead+len(group.members)
        return {'min_rank':low,'max_rank':high+missing,
                'missing_runner_count':missing,
                'basis':'source_notation_bounds_not_continuous_tracking'}
    raise ValueError('target absent')


def progress_band(previous: dict, current: dict) -> dict:
    low=previous['min_rank']-current['max_rank']
    high=previous['max_rank']-current['min_rank']
    return {'min_places_gained':low,'max_places_gained':high,
            'confirmed_advanced':low>0,'confirmed_dropped':high<0,
            'unresolved_or_unchanged':low<=0<=high}
