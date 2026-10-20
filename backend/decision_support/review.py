"""Append-only human annotations and versioned exports; never edits original plays."""
import csv
import io
import json
from collections import Counter
from datetime import date

from .game import COVERAGES, advance_play, integer
from .playbook import PERSONNEL, FORMATIONS, get_call
from .store import now, public_session

from .execution import validate_execution, execution_blockers

REVIEW_VERSION = 2
KINDS = ['gain', 'incomplete', 'sack', 'turnover', 'touchdown', 'safety']
PENALTIES = ['unknown', 'none', 'declined', 'accepted', 'offsetting']


def validate_review(data, play):
    fields = {'status', 'reviewer', 'source_type', 'source_reference', 'game_id', 'game_date', 'actual_call_id',
              'actual_personnel', 'actual_formation', 'observed_coverage', 'actual_kind', 'actual_yards',
              'penalty_status', 'outcome_verified', 'before_state_verified', 'notes'}
    if not isinstance(data, dict) or set(data) - {'source_play_id', 'execution'} != fields:
        raise ValueError('Provide the complete review with the documented fields')
    result = {**data, 'source_play_id': data.get('source_play_id', '')}
    for key, choices in [('status', ['draft', 'approved', 'excluded']),
                         ('source_type', ['unknown', 'real_game', 'practice', 'test']),
                         ('actual_personnel', ['unknown'] + [k for k in PERSONNEL if k != 'any']),
                         ('actual_formation', ['unknown'] + [k for k in FORMATIONS if k != 'any']),
                         ('observed_coverage', COVERAGES), ('actual_kind', KINDS), ('penalty_status', PENALTIES)]:
        if not isinstance(result[key], str) or result[key] not in choices:
            raise ValueError(f'Unsupported {key}')
    for key in ['reviewer', 'source_reference', 'game_id', 'game_date', 'source_play_id', 'actual_call_id', 'notes']:
        if not isinstance(result[key], str) or len(result[key]) > (2000 if key == 'notes' else 300):
            raise ValueError(f'Invalid {key}')
        result[key] = result[key].strip()
    if not result['reviewer']:
        raise ValueError('Name the reviewer (self-reported; no account authentication)')
    for key in ['outcome_verified', 'before_state_verified']:
        if type(result[key]) is not bool:
            raise ValueError(f'{key} must be true or false')
    result['actual_yards'] = integer(result['actual_yards'], 'actual_yards', -99, 99)
    if result['game_date']:
        try:
            date.fromisoformat(result['game_date'])
        except ValueError:
            raise ValueError('Game date must be YYYY-MM-DD') from None
    if result['actual_call_id'] != 'unknown':
        call = get_call(result['actual_call_id'])
        if play.get('historical_source') and call['type'].lower() != play['action']:
            raise ValueError('Concept action disagrees with the source play intent; exclude or resolve this source record')
        if call['type'] == 'RUN' and result['actual_kind'] in ('sack', 'incomplete'):
            raise ValueError('Sacks and incompletions require an actual pass concept')
    if result['status'] == 'excluded' and not result['notes']:
        raise ValueError('Explain why this record is excluded')
    if result['status'] == 'approved':
        if (any(result[k] == 'unknown' for k in ['actual_call_id', 'actual_personnel', 'actual_formation', 'source_type', 'penalty_status'])
                or not all(result[k] for k in ['source_reference', 'game_id', 'game_date']) or not result['outcome_verified'] or not result['before_state_verified']):
            raise ValueError('Approval requires verified pre-snap state, concept, personnel, formation, outcome, penalty status, source, game ID, and game date')
        source = play.get('historical_source')
        if source and any(result[key] != source[source_key] for key, source_key in [('game_id', 'game_id'), ('source_play_id', 'play_id'), ('game_date', 'game_date')]):
            raise ValueError('Historical source game, play ID, and date must match the imported evidence')
        # Validate physical outcome consistency without changing the saved game.
        advance_play(play['before'], dict(kind=result['actual_kind'], yards=result['actual_yards'], elapsed_seconds=0))
    changed = (play['call_id'] != 'unlabeled' and result['actual_call_id'] not in ('unknown', play['call_id'])) or result['actual_kind'] != play['outcome']['kind'] or result['actual_yards'] != play['outcome']['yards']
    if changed and not result['notes']:
        raise ValueError('Explain corrections to the original concept or outcome in notes')
    if 'execution' in data:
        result['execution'] = validate_execution(data['execution'], result, play)
    return result


def readiness(play):
    history = play.get('reviews', [])
    review = history[-1] if history else None
    reasons = []
    if not review or review['status'] != 'approved':
        reasons.append('Latest review is not approved')
    if not review or review['source_type'] != 'real_game':
        reasons.append('Not verified as a real game')
    if not review or review['penalty_status'] not in ('none', 'declined'):
        reasons.append('Penalty absent, unresolved, or affects the play')
    context = play.get('decision_context')
    if not context or not context.get('situation') or not context.get('preferences'):
        reasons.append('Original decision-time context is missing')
    if not review or not review.get('before_state_verified'):
        reasons.append('Pre-snap game state has not been verified')
    # Corrections do not silently repair later states or the original feature snapshot.
    if review and (review['actual_kind'] != play['outcome']['kind'] or review['actual_yards'] != play['outcome']['yards']):
        reasons.append('Outcome correction requires game-state reconciliation before training')
    defense_reasons = reasons + ([] if review and review['observed_coverage'] != 'UNKNOWN' else ['Observed coverage is unknown'])
    design_reasons = reasons + execution_blockers(review)
    return dict(design_candidate=not design_reasons, design_blockers=design_reasons, yardage_candidate=not reasons, yardage_blockers=reasons,
                defensive_label_candidate=not defense_reasons, defensive_label_blockers=defense_reasons,
                epa_candidate=False, epa_blockers=['No independently computed or verified EPA target'],
                scope='Annotation candidates only; dataset validation, chronological splits, and model evaluation still required')


def session_rows(session):
    return [dict(session_id=session['id'], session_revision=session['revision'], play_id=play['id'],
                 original=play, latest_review=(play.get('reviews') or [None])[-1], readiness=readiness(play))
            for play in session['plays']]


def session_export(session):
    return dict(schema_version=1, exported_at=now(), session=public_session(session), records=session_rows(session),
                field_notes=dict(original='Immutable recorded play, including decision context and review history',
                                 latest_review='Latest human annotation, not a change to the original game state',
                                 reviewer='Self-reported name; this local service has no account authentication',
                                 readiness='Target-specific candidate checks, not a training certification',
                                 epa='Unavailable for manually recorded outcomes; never inferred from recommendations'))


def csv_export(session):
    columns = ['schema_version', 'session_id', 'session_revision', 'play_id', 'recorded_call_id', 'recorded_kind',
               'recorded_yards', 'review_status', 'reviewer', 'source_type', 'source_reference', 'game_id', 'game_date', 'source_play_id',
               'actual_call_id', 'actual_personnel', 'actual_formation', 'observed_coverage', 'actual_kind', 'actual_yards',
               'penalty_status', 'outcome_verified', 'before_state_verified', 'notes', 'yardage_candidate', 'defensive_label_candidate', 'epa_candidate',
               'execution_json', 'readiness_json', 'before_json', 'after_json', 'decision_context_json', 'original_outcome_json', 'review_history_json']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for row in session_rows(session):
        play, review = row['original'], row['latest_review'] or {}
        values = {key: review.get(key, '') for key in columns}
        values.update(schema_version=1, session_id=session['id'], session_revision=session['revision'], play_id=play['id'],
                      recorded_call_id=play['call_id'], recorded_kind=play['outcome']['kind'], recorded_yards=play['outcome']['yards'],
                      review_status=review.get('status', 'unreviewed'),
                      **{k: row['readiness'][k] for k in ['yardage_candidate', 'defensive_label_candidate', 'epa_candidate']})
        for key, value in [('execution', review.get('execution')), ('readiness', row['readiness']), ('before', play['before']), ('after', play['after']),
                           ('decision_context', play.get('decision_context')), ('original_outcome', play['outcome']), ('review_history', play.get('reviews', []))]:
            values[key + '_json'] = json.dumps(value, separators=(',', ':'), ensure_ascii=False)
        # Preserve raw text in JSON; avoid spreadsheet formula execution in CSV text cells.
        values = {key: "'" + value if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')) else value for key, value in values.items()}
        writer.writerow(values)
    return stream.getvalue()


def review_summary(sessions):
    rows = [row for session in sessions for row in session_rows(session)]
    return dict(recorded_plays=len(rows), statuses=dict(Counter((row['latest_review'] or {}).get('status', 'unreviewed') for row in rows)),
                yardage_candidates=sum(row['readiness']['yardage_candidate'] for row in rows),
                defensive_label_candidates=sum(row['readiness']['defensive_label_candidate'] for row in rows),
                epa_candidates=0)


def register_review_routes(app, store, data_dir):
    from flask import Response, jsonify, request
    from .audit import audit_sources

    @app.get('/api/data/audit')
    def data_audit():
        return jsonify(historical=audit_sources(data_dir), recorded=review_summary(store.list()))

    @app.get('/api/sessions/<session_id>/review')
    def review_queue(session_id):
        session = store.get(session_id)
        return jsonify(session_id=session_id, revision=session['revision'], records=session_rows(session))

    @app.post('/api/sessions/<session_id>/plays/<play_id>/review')
    def save_review(session_id, play_id):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) != {'revision', 'mutation_id', 'review'}:
            raise ValueError('Provide revision, mutation_id, and review')

        def apply(session):
            play = next((play for play in session['plays'] if play['id'] == play_id), None)
            if play is None:
                raise KeyError('Recorded play not found')
            annotation = validate_review(payload['review'], play)
            history = play.setdefault('reviews', [])
            history.append(dict(**annotation, schema_version=REVIEW_VERSION, review_number=len(history) + 1,
                                reviewed_at=now(), based_on_session_revision=session['revision']))
            # A reviewed play must not disappear via Undo; corrections remain annotations.
            session['_undo'] = None
        session = store.mutate(session_id, payload, 'review:' + play_id, apply)
        return jsonify(public_session(session))

    @app.get('/api/sessions/<session_id>/export')
    def export(session_id):
        session = store.get(session_id)
        format = request.args.get('format', 'json')
        if format not in ('json', 'csv'):
            raise ValueError('Export format must be json or csv')
        response = jsonify(session_export(session)) if format == 'json' else Response(csv_export(session), mimetype='text/csv')
        response.headers['Content-Disposition'] = f'attachment; filename="digitaloc-{session["id"]}.{format}"'
        response.headers['Cache-Control'] = 'no-store'
        return response
