"""Browse real local PBP sources and stage unlabeled records for human review."""
import hashlib
import json
import re
from functools import lru_cache
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .data import FEATURES, TEAM_ALIASES
from .dataset import TEAMS
from .game import DEFAULT_STATE, integer
from .playbook import default_preferences
from .store import now, public_session

FIELDS = list(dict.fromkeys(FEATURES + ['game_id', 'play_id', 'game_date', 'desc', 'posteam_score', 'defteam_score',
    'quarter_seconds_remaining', 'play_type', 'yards_gained', 'epa', 'penalty', 'qb_kneel', 'qb_spike', 'qb_scramble',
    'qb_dropback', 'sack', 'interception', 'fumble_lost', 'touchdown', 'safety', 'incomplete_pass', 'drive']))
PART_FIELDS = ['nflverse_game_id', 'play_id', 'route', 'offense_formation', 'offense_personnel', 'defense_coverage_type']


@lru_cache(maxsize=1024)
def source_date(value):
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return datetime.strptime(value, '%m/%d/%Y').date().isoformat()


def validate_source_state(state):
    # Scalar equivalent of the dashboard state ranges; avoid creating a pandas
    # frame per historical row. The dataset builder revalidates staged states.
    state = dict(state)
    for key, low, high in [('offense_score', 0, 100), ('defense_score', 0, 100), ('qtr', 1, 4),
                          ('quarter_seconds_remaining', 1, 900), ('down', 1, 4), ('ydstogo', 1, 99),
                          ('yardline_100', 1, 99), ('posteam_timeouts_remaining', 0, 3), ('defteam_timeouts_remaining', 0, 3)]:
        state[key] = integer(state[key], key, low, high)
    for key in ['posteam', 'defteam']:
        team = str(state[key]).strip().upper()
        state[key] = TEAM_ALIASES.get(team, team)
        if state[key] not in TEAMS:
            raise ValueError('Unsupported team')
    if state['posteam'] == state['defteam'] or state['ydstogo'] > state['yardline_100']:
        raise ValueError('Invalid source situation')
    return state


def source_season(root, season):
    if type(season) is not int or not 2020 <= season <= 2024:
        raise ValueError('Choose a local season from 2020 through 2024')
    paths = [Path(root) / f'pbp_{season}_{shard}.csv' for shard in (0, 1)] + [Path(root) / f'pbp_participation_{season}.csv']
    if any(not path.exists() for path in paths):
        raise ValueError('This season is missing a PBP shard or participation source')
    signature = tuple((str(p.resolve()), p.stat().st_size, p.stat().st_mtime_ns) for p in paths)
    return _load(signature)


@lru_cache(maxsize=2)
def _load(signature):
    frames = []
    for path, _, _ in signature[:2]:
        frame = pd.read_csv(path, usecols=lambda key: key in FIELDS, low_memory=False)
        frame['_file'] = Path(path).name
        frames.append(frame)
    pbp = pd.concat(frames, ignore_index=True)
    part = pd.read_csv(signature[2][0], usecols=lambda key: key in PART_FIELDS, low_memory=False).rename(columns={'nflverse_game_id': 'game_id'})
    for frame in (pbp, part):
        if not {'game_id', 'play_id'} <= set(frame):
            raise ValueError('Source game/play keys are missing')
        frame['play_id'] = pd.to_numeric(frame['play_id'], errors='coerce')
        if frame[['game_id', 'play_id']].isna().any().any() or frame.duplicated(['game_id', 'play_id']).any():
            raise ValueError('Missing or duplicate source keys; resolve the data audit first')
    if not {'play_type', 'qb_kneel', 'qb_spike', 'penalty'} <= set(pbp):
        raise ValueError('Required eligibility fields are missing')
    pbp = pbp.loc[pbp.play_type.isin(['run', 'pass']) & pbp.qb_kneel.eq(0) & pbp.qb_spike.eq(0) & pbp.penalty.eq(0)].copy()
    merged = pbp.merge(part, on=['game_id', 'play_id'], how='left', validate='one_to_one')
    records = []
    for raw in merged.to_dict('records'):
        # JSON-safe scalars; preserve unknown labels instead of inventing mappings.
        raw = {key: None if pd.isna(value) else value for key, value in raw.items()}
        try:
            state = {**DEFAULT_STATE, **{k: raw[k] for k in ['posteam', 'defteam', 'down', 'ydstogo', 'yardline_100', 'qtr',
                     'quarter_seconds_remaining', 'posteam_timeouts_remaining', 'defteam_timeouts_remaining']},
                     'offense_score': raw['posteam_score'], 'defense_score': raw['defteam_score']}
            state = validate_source_state(state)
            if raw['yards_gained'] is None or not float(raw['yards_gained']).is_integer() or not -99 <= raw['yards_gained'] <= 99:
                continue
            yards = int(raw['yards_gained'])
            kind = ('turnover' if raw.get('interception') == 1 or raw.get('fumble_lost') == 1 else
                    'touchdown' if raw.get('touchdown') == 1 else 'safety' if raw.get('safety') == 1 else
                    'sack' if raw.get('sack') == 1 else 'incomplete' if raw.get('incomplete_pass') == 1 else 'gain')
            if not isinstance(raw.get('game_date'), str):
                continue
            game_date = source_date(raw['game_date'])
            if not float(raw['play_id']).is_integer():
                continue
            action = 'pass' if raw['play_type'] == 'pass' or any(raw.get(k) == 1 for k in ('qb_dropback', 'qb_scramble', 'sack')) else 'run'
            source = dict(provider='Local nflverse CSVs', game_id=raw['game_id'], play_id=str(int(raw['play_id'])),
                          game_date=game_date, pbp_file=raw['_file'], participation_file=Path(signature[2][0]).name,
                          description=raw.get('desc') or '', raw_labels={k: raw.get(k) for k in PART_FIELDS[2:]},
                          observed_epa=raw.get('epa'), penalty_flag=raw['penalty'], original_play_type=raw['play_type'],
                          source_fields=raw)
            digest = hashlib.sha256(json.dumps(source, sort_keys=True, allow_nan=False).encode()).hexdigest()
            records.append(dict(game_id=source['game_id'], play_id=source['play_id'], game_date=game_date, action=action,
                                before=state, outcome=dict(kind=kind, yards=yards, elapsed_seconds=None, observed_coverage='UNKNOWN'),
                                source=source, source_sha256=digest, drive=int(raw.get('drive') or 1)))
        except (ValueError, TypeError, KeyError):
            continue
    return records


def import_record(record):
    return dict(id='source-' + record['play_id'], call_id='unlabeled', name='Unlabeled historical ' + record['action'],
                action=record['action'], before=record['before'], after=None, outcome=record['outcome'], drive=record['drive'],
                created_at=now(), historical_source=record['source'], source_sha256=record['source_sha256'],
                decision_context=dict(context_origin='historical_pre_snap_reconstruction', situation=record['before'],
                                      preferences=default_preferences(), suggestions=[], displayed_candidate_ids=None,
                                      display_source='not_reported', catalog_version=None, rule_version=None, outcome_model_id=None),
                reviews=[])


def register_labeling_routes(app, store, data_dir):
    from flask import jsonify, request

    def season_arg():
        try:
            return int(request.args.get('season', '2024'))
        except ValueError:
            raise ValueError('Season must be an integer') from None

    @app.get('/api/labeling/games')
    def games():
        records = source_season(data_dir, season_arg())
        grouped = {}
        for record in records:
            game = grouped.setdefault(record['game_id'], dict(game_id=record['game_id'], game_date=record['game_date'], plays=0, run=0, pass_count=0))
            game['plays'] += 1
            game['run' if record['action'] == 'run' else 'pass_count'] += 1
        return jsonify(games=sorted(grouped.values(), key=lambda game: (game['game_date'], game['game_id'])),
                       scope='Penalty-free regulation run/pass candidates with valid pre-snap fields; no full concepts inferred')

    @app.get('/api/labeling/plays')
    def plays():
        records = source_season(data_dir, season_arg())
        game_id = request.args.get('game_id', '')
        action = request.args.get('action', 'all')
        if action not in ('all', 'run', 'pass'):
            raise ValueError('Action must be all, run, or pass')
        try:
            page = int(request.args.get('page', '0'))
            if page < 0:
                raise ValueError()
        except ValueError:
            raise ValueError('Page must be a nonnegative integer') from None
        selected = sorted((r for r in records if r['game_id'] == game_id and (action == 'all' or r['action'] == action)), key=lambda r: int(r['play_id']))
        if not any(r['game_id'] == game_id for r in records):
            raise KeyError('Source game not found')
        return jsonify(total=len(selected), page=page, page_size=20, plays=selected[page * 20:(page + 1) * 20])

    @app.post('/api/labeling/import')
    def stage():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) != {'game_id', 'play_ids'}:
            raise ValueError('Provide game_id and play_ids')
        game_id, ids = payload['game_id'], payload['play_ids']
        if not isinstance(game_id, str) or not re.fullmatch(r'20\d\d_[A-Za-z0-9_]+', game_id):
            raise ValueError('Use the canonical source game ID')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 50 or any(not isinstance(id, str) for id in ids) or len(set(ids)) != len(ids):
            raise ValueError('Choose 1–50 unique source play IDs')
        found = {r['play_id']: r for r in source_season(data_dir, int(game_id[:4])) if r['game_id'] == game_id and r['play_id'] in ids}
        if set(found) != set(ids):
            raise ValueError('Some selected source plays are missing or ineligible')
        records = [import_record(found[id]) for id in sorted(ids, key=int)]
        return jsonify(public_session(store.stage_historical(game_id, records)))
