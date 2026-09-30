"""Build explicit X/Y from already normalized records. No scraping or training.

The field adapter must establish current-entry field availability. This module
uses an allow-list; it does not prove that a historical page existed at as_of.
"""
from __future__ import annotations
from datetime import datetime
import hashlib
import itertools
import json
from gi_racesim.normalization.asof import eligible_history
from gi_racesim.normalization.corners import parse_corner, pair_observation

ENTRY_KEYS=('horse_id','gate_no','frame_no','sex','age','carried_kg','jockey_id')
HISTORY_KEYS=('race_id','event_at','course','surface','distance_m','class_code',
              'going','field_size','gate_no','jockey_id','carried_kg',
              'corner_ranks','finish_s','last600_s','laps_s','history_quality')


def build_example(*, race_id: str, target_start: str, as_of: str, mode: str,
                  condition: dict, entries: list[dict], history_records: list[dict],
                  corner_observations: list[dict], lap_observation: dict | None,
                  history_limit: int=12, lookback_days: int=1096) -> dict:
    if mode not in {'retrospective','prospective'} or history_limit<1 or lookback_days<1:
        raise ValueError('invalid mode or history settings')
    cutoff=datetime.fromisoformat(as_of)
    start=datetime.fromisoformat(target_start)
    if cutoff.tzinfo is None or start.tzinfo is None or cutoff>=start:
        raise ValueError('aware as_of before target_start required')
    ids=[e['horse_id'] for e in entries]
    numbers=[e['gate_no'] for e in entries]
    if len(ids)!=len(set(ids)) or len(numbers)!=len(set(numbers)) or any(n<1 for n in numbers):
        raise ValueError('unique horse IDs and positive gate numbers required')
    runners=[]
    for e in sorted(entries,key=lambda e:e['gate_no']):
        past=[r for r in history_records if r.get('horse_id')==e['horse_id']
              and eligible_history(r,target_start=target_start,as_of=as_of,mode=mode)]
        # Keep the latest observed start calculation separate from the context window.
        past.sort(key=lambda r:datetime.fromisoformat(r['event_at']),reverse=True)
        dedup=[]
        seen=set()
        for r in past:
            if r['race_id'] not in seen:
                dedup.append(r); seen.add(r['race_id'])
            else:
                raise ValueError('multiple versions of historical race: resolve in manifest first')
        recent=[r for r in dedup if (cutoff-datetime.fromisoformat(r['event_at'])).days<=lookback_days][:history_limit]
        runners.append({
            'entry':{k:e.get(k) for k in ENTRY_KEYS},
            'days_since_latest_observed_start':None if not dedup else
                (cutoff-datetime.fromisoformat(dedup[0]['event_at'])).total_seconds()/86400,
            'history_count':len(recent),
            'history_complete':bool(e.get('history_complete',False)),
            'history':[ {k:r.get(k) for k in HISTORY_KEYS} for r in reversed(recent) ],
        })
    targets=[]
    for obs in corner_observations:
        if obs.get('notation') is None:
            targets.append({'checkpoint':obs['checkpoint'],'observed':False,'pairs':[]})
            continue
        c=parse_corner(obs['notation'])
        if not set(c.horses).issubset(numbers):
            raise ValueError('corner has a runner outside the declared field')
        pairs=[]
        for a,b in itertools.combinations(sorted(c.horses),2):
            p=pair_observation(c,a,b)
            pairs.append({'a':a,'b':b,**p,
                          'front_mask':p['a_before_b'] is not None,
                          'inside_mask':p['a_inside_b'] is not None})
        targets.append({'checkpoint':obs['checkpoint'],'observed':True,
                        'source_id':obs.get('source_id'), 'parsed':c.to_dict(),
                        'observed_gate_numbers':list(c.horses),
                        'unobserved_gate_numbers':sorted(set(numbers)-set(c.horses)),
                        'full_roster_observed':set(c.horses)==set(numbers),
                        'pairs':pairs})
    lap_ok=lap_observation is not None and lap_observation.get('complete') is True
    corner_any=any(t['observed'] for t in targets)
    grammar_ok=any(t['observed'] and t['full_roster_observed'] for t in targets)
    return {
        'meta':{'race_id':race_id,'target_start':target_start,'as_of':as_of,'mode':mode},
        'X':{'condition':{k:condition.get(k) for k in
                         ('course','surface','distance_m','class_code','going','declared_field_size')},
             'runners':runners},
        'Y':{'laps':lap_observation,'corners':targets},
        'training_routes':{
            'lap_loss':lap_ok,
            'conditional_corner_loss':lap_ok and grammar_ok,
            'unconditional_corner_auxiliary':corner_any,
            'incomplete_roster_needs_latent_or_partial_loss':corner_any and not grammar_ok,
        },
        'notes':['No target finishing order is copied into X.',
                 'Missing laps are not replaced by zero or average teacher values.',
                 'Future DNF status is not a pre-race roster mask.',
                 'No continuous coordinates or simulation accuracy established.'],
    }


def freeze_manifest(*, sources: list[dict], splits: dict[str,list[str]],
                    parser_version: str, feature_version: str) -> dict:
    """Versions must specify exact source content hashes, not mutable URLs only."""
    if not parser_version or not feature_version:
        raise ValueError('versions required')
    all_ids=[r for races in splits.values() for r in races]
    if len(all_ids)!=len(set(all_ids)):
        raise ValueError('a race cannot occur in multiple splits')
    source_keys=[]
    for s in sources:
        if not s.get('source_id') or len(s.get('sha256',''))!=64:
            raise ValueError('exact source ID and SHA256 required')
        source_keys.append(s['source_id'])
    if len(source_keys)!=len(set(source_keys)):
        raise ValueError('duplicate source version ID')
    body={'sources':sorted(sources,key=lambda s:s['source_id']),
          'splits':{k:sorted(v) for k,v in sorted(splits.items())},
          'parser_version':parser_version,'feature_version':feature_version}
    digest=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,
                                   separators=(',',':')).encode()).hexdigest()
    return {'dataset_hash':digest, **body}
