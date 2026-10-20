"""Build a reproducible concept-yardage dataset from reviewed local sessions.

This validates and exports candidates; it does not fit or promote a model.
"""
import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from .data import FEATURES
from .game import model_situation, validate_state
from .playbook import CATALOG_VERSION, PLAYBOOK
from .review import readiness, validate_review
from .execution import execution_blockers

VERSION = 'concept-dataset-3'
TEAMS = 'ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LA LAC LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS'.split()
# Planning gates, not statistical guarantees or a claim of deployment readiness.
MIN_ROWS = dict(train=100, validation=20, test=20)
MIN_GAMES = dict(train=3, validation=2, test=2)
REVIEW_FIELDS = ['status', 'reviewer', 'source_type', 'source_reference', 'game_id', 'game_date', 'source_play_id',
                 'actual_call_id', 'actual_personnel', 'actual_formation', 'observed_coverage', 'actual_kind',
                 'actual_yards', 'penalty_status', 'before_state_verified', 'outcome_verified', 'notes']


def source_id(value):
    """Canonical whitespace/case only; callers must use one source ID convention."""
    return value.strip().upper() if isinstance(value, str) else ''


def iso_date(value):
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError('Use an ISO game date (YYYY-MM-DD)')
    return value


def build_dataset(sessions, train_through=None, validation_through=None):
    sessions = sorted(sessions, key=lambda item: item['id'])
    if bool(train_through) != bool(validation_through):
        raise ValueError('Supply both train_through and validation_through, or neither')
    if train_through:
        iso_date(train_through); iso_date(validation_through)
        if train_through >= validation_through:
            raise ValueError('Training cutoff must precede validation cutoff')
    source_digest = hashlib.sha256(json.dumps(sessions, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    entries, groups, games = [], defaultdict(list), defaultdict(list)
    catalog = {call['id']: call for call in PLAYBOOK}
    for session in sessions:
        upstream_problem = False
        for play in session['plays']:
            review = (play.get('reviews') or [None])[-1]
            entry = dict(session_id=session['id'], session_revision=session['revision'], recorded_play_id=play['id'],
                         source_game_id=source_id((review or {}).get('game_id')),
                         source_play_id=source_id((review or {}).get('source_play_id')), blockers=[])
            entries.append(entry)
            if entry['source_game_id'] and entry['source_play_id'] and review.get('source_type') == 'real_game' and review.get('status') != 'excluded':
                groups[(entry['source_game_id'], entry['source_play_id'])].append(entry)
            entry['blockers'].extend(readiness(play)['yardage_blockers'])
            if not entry['source_play_id']:
                entry['blockers'].append('missing_source_play_id')
            if not entry['source_game_id']:
                entry['blockers'].append('missing_source_game_id')
            if review and (review.get('actual_yards') != play['outcome']['yards'] or review.get('actual_kind') != play['outcome']['kind'] or review.get('penalty_status') in ('accepted', 'offsetting')):
                upstream_problem = True
            if upstream_problem:
                entry['blockers'].append('unreconciled_outcome_or_penalty_in_session_history')
            if not review:
                continue
            try:
                # Revalidate labels instead of trusting a persisted readiness flag.
                checked = validate_review({**{k: review.get(k, '' if k == 'source_play_id' else None) for k in REVIEW_FIELDS}, **({'execution': review['execution']} if 'execution' in review else {})}, play)
                iso_date(checked['game_date'])
                before = validate_state(play['before'], TEAMS)
                context = play.get('decision_context') or {}
                if context.get('situation') != play['before']:
                    raise ValueError('Decision snapshot does not match recorded pre-snap state')
                entry['game_date'] = checked['game_date']
                entry['team_pair'] = sorted([before['posteam'], before['defteam']])
                if entry['source_game_id'] and review['source_type'] == 'real_game' and review['status'] != 'excluded':
                    games[entry['source_game_id']].append(entry)
                call = catalog.get(checked['actual_call_id'])
                if call is None:
                    raise ValueError('Unknown concept mapping')
                entry['row'] = dict(session_id=session['id'], recorded_play_id=play['id'], source_game_id=entry['source_game_id'],
                                   source_play_id=entry['source_play_id'], game_date=checked['game_date'],
                                   features=model_situation(before), action=dict(concept_id=call['id'], type=call['type'].lower()),
                                   targets=dict(yards_gained=checked['actual_yards']),
                                   design_review=dict(planned=context.get('play_design'), executed=checked.get('execution'),
                                                      actual_personnel=checked['actual_personnel'], actual_formation=checked['actual_formation'],
                                                      blockers=execution_blockers(checked)),
                                   provenance=dict(context_origin=context.get('context_origin', 'live_coach_session'),
                                                   source_row_sha256=play.get('source_sha256'),
                                                   source_files={key: (play.get('historical_source') or {}).get(key) for key in ('pbp_file', 'participation_file')},
                                                   review_number=review.get('review_number'), reviewer=checked['reviewer'],
                                                   source_reference=checked['source_reference'], catalog_version=CATALOG_VERSION,
                                                   recorded_catalog_version=context.get('catalog_version'),
                                                   rule_version=context.get('rule_version'), outcome_model_id=context.get('outcome_model_id')))
            except (ValueError, TypeError, KeyError) as error:
                entry['blockers'].append('invalid_record: ' + str(error))
    duplicates = []
    for (game_id, play_id), group in sorted(groups.items()):
        if len(group) > 1:
            duplicates.append(dict(source_game_id=game_id, source_play_id=play_id, occurrences=len(group)))
            for entry in group:
                entry['blockers'].append('duplicate_source_play_requires_resolution')
    conflicts = []
    for game_id, group in sorted(games.items()):
        if len({(entry['game_date'], tuple(entry['team_pair'])) for entry in group}) > 1:
            conflicts.append(game_id)
            for entry in group:
                entry['blockers'].append('conflicting_game_date_or_teams')
    rows, excluded = [], []
    for entry in entries:
        if entry['blockers']:
            excluded.append({key: entry[key] for key in ['session_id', 'recorded_play_id', 'source_game_id', 'source_play_id']} | {'blockers': sorted(set(entry['blockers']))})
        elif 'row' in entry:
            rows.append(entry['row'])
    rows.sort(key=lambda row: (row['game_date'], row['source_game_id'], row['source_play_id'], row['session_id'], row['recorded_play_id']))
    dates = sorted({row['game_date'] for row in rows})
    strategy = 'explicit_date_cutoffs' if train_through else 'chronological_date_groups_60_20_20'
    if not train_through and len(dates) >= 3:
        train_count = max(1, min(len(dates) - 2, int(len(dates) * .6)))
        validation_count = max(1, min(len(dates) - train_count - 1, int(len(dates) * .2)))
        train_through = dates[train_count - 1]
        validation_through = dates[train_count + validation_count - 1]
    for row in rows:
        row['split'] = ('train' if row['game_date'] <= train_through else 'validation' if row['game_date'] <= validation_through else 'test') if train_through else 'unassigned'
    support = []
    for concept in sorted(catalog):
        selected = [row for row in rows if row['action']['concept_id'] == concept]
        counts = {split: sum(row['split'] == split for row in selected) for split in MIN_ROWS}
        game_counts = {split: len({row['source_game_id'] for row in selected if row['split'] == split}) for split in MIN_ROWS}
        support.append(dict(concept_id=concept, rows=counts, games=game_counts,
                            meets_planning_gate=all(counts[split] >= MIN_ROWS[split] and game_counts[split] >= MIN_GAMES[split] for split in MIN_ROWS)))
    gates = []
    if not rows:
        gates.append('No eligible reviewed real-game records')
    if not train_through:
        gates.append('At least three distinct game dates are needed for automatic splits')
    for split in MIN_ROWS:
        if not any(row['split'] == split for row in rows):
            gates.append(f'No records in {split} split')
    if sum(item['meets_planning_gate'] for item in support) < 2:
        gates.append('At least two concepts must meet the per-split sample and game planning gates')
    design_rows = [row for row in rows if not row['design_review']['blockers']]
    design_support = []
    for concept, formation in sorted({(row['action']['concept_id'], row['design_review']['actual_formation']) for row in design_rows}):
        selected = [row for row in design_rows if row['action']['concept_id'] == concept and row['design_review']['actual_formation'] == formation]
        counts = {split: sum(row['split'] == split for row in selected) for split in MIN_ROWS}
        game_counts = {split: len({row['source_game_id'] for row in selected if row['split'] == split}) for split in MIN_GAMES}
        design_support.append(dict(concept_id=concept, formation=formation, rows=counts, games=game_counts,
                                   meets_planning_gate=all(counts[k] >= MIN_ROWS[k] and game_counts[k] >= MIN_GAMES[k] for k in MIN_ROWS)))
    design_readiness = dict(verified_eligible_plays=len(design_rows), support=design_support,
        missing_labels=dict(Counter(reason for row in rows for reason in row['design_review']['blockers'])),
        status='planning_gates_met' if sum(item['meets_planning_gate'] for item in design_support) >= 2 else 'blocked',
        scope='Verified execution annotations only; not model input features. Counts include only records passing the full concept dataset validation.')
    config = dict(schema_version=VERSION, catalog_version=CATALOG_VERSION, features=FEATURES, targets=['yards_gained'],
                  split_strategy=strategy, train_through=train_through, validation_through=validation_through,
                  minimum_rows_per_concept=MIN_ROWS, minimum_games_per_concept=MIN_GAMES)
    digest = hashlib.sha256(json.dumps(dict(source_digest=source_digest, config=config, rows=rows, excluded=excluded), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return dict(dataset_id='concept-' + digest[:16], sha256=digest, source_sha256=source_digest, config=config,
                status='blocked' if gates else 'eligible_for_experimental_training', training_blockers=gates,
                summary=dict(recorded_plays=len(entries), included_plays=len(rows), excluded_plays=len(excluded),
                             unique_games=len({row['source_game_id'] for row in rows}), duplicate_source_groups=len(duplicates),
                             conflicting_games=len(conflicts), splits=dict(Counter(row['split'] for row in rows))),
                design_readiness=design_readiness, concept_support=support, duplicates=duplicates, conflicting_game_ids=conflicts, exclusions=excluded, rows=rows,
                limitations=[
                    'Planning thresholds are configurable in code, not evidence of statistical power or deployment readiness.',
                    'Use consistent source game/play IDs across sessions. Different aliases cannot be deduplicated automatically.',
                    'All non-excluded copies of duplicate source plays are quarantined; explicitly exclude duplicate copies to resolve them.',
                    'Observed coverage, actual personnel/formation, final state, model estimates, and route coordinates are excluded from features.',
                    'Only verified yardage is exported as a target. No concept EPA, conversion, or defensive-response model is trained.',
                    'Actual concept is the action being evaluated, not a target to imitate historical coaching choices.',
                    'Freeze a dated dataset and cutoffs before experiments; adding records can change automatic boundaries.',
                    'Human labels require independent spot checks. Review approval alone does not prove label accuracy.',
                ])


def register_dataset_routes(app, store):
    from flask import jsonify, request

    @app.get('/api/data/dataset')
    def dataset():
        if set(request.args) - {'download', 'train_through', 'validation_through'}:
            raise ValueError('Unsupported dataset parameter')
        result = build_dataset(store.list(), request.args.get('train_through'), request.args.get('validation_through'))
        if request.args.get('download') not in (None, '1'):
            raise ValueError('download must be 1 when supplied')
        response = jsonify(result if request.args.get('download') == '1' else {key: value for key, value in result.items() if key != 'rows'})
        response.headers['Cache-Control'] = 'no-store'
        if request.args.get('download') == '1':
            response.headers['Content-Disposition'] = f'attachment; filename="{result["dataset_id"]}.json"'
        return response


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=Path(__file__).resolve().parents[1] / 'instance' / 'digitaloc.sqlite')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--train-through')
    parser.add_argument('--validation-through')
    args = parser.parse_args()
    # Read-only connection: missing input must not create an empty database.
    with sqlite3.connect(args.db.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        sessions = [json.loads(row[0]) for row in connection.execute('SELECT body FROM sessions ORDER BY id')]
    result = build_dataset(sessions, args.train_through, args.validation_through)
    args.output.mkdir(parents=True, exist_ok=True)
    artifact = args.output / (result['dataset_id'] + '.json')
    with artifact.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(path=str(artifact), status=result['status'], summary=result['summary'], training_blockers=result['training_blockers']), indent=2))
