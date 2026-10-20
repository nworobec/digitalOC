"""Session-scoped schematic positions; no model features or formation-legality claim."""
import math
import copy
from .playbook import get_call, default_preferences
from .designs import validate_design
from .store import public_session, now

DEFAULT_POSITIONS = [[76, 202], [160, 202], [250, 202], [280, 202], [310, 202], [340, 202], [370, 202], [462, 202], [544, 202], [310, 244], [366, 266]]


def validate_positions(value):
    if not isinstance(value, list) or len(value) != 11:
        raise ValueError('Provide exactly 11 offensive player positions')
    cleaned = []
    for point in value:
        if not isinstance(point, list) or len(point) != 2 or any(type(n) not in (int, float) or not math.isfinite(n) for n in point):
            raise ValueError('Each player position must contain two finite coordinates')
        x, y = point
        if not 20 <= x <= 600 or not 202 <= y <= 290:
            raise ValueError('Keep offensive players inside the field and on the offensive side of the line')
        cleaned.append([round(x, 1), round(y, 1)])
    if any(math.dist(a, b) < 18 for i, a in enumerate(cleaned) for b in cleaned[i + 1:]):
        raise ValueError('Separate overlapping player markers before saving')
    return cleaned


def call_layout(session, call_id):
    return session.get('layouts', {}).get(call_id, dict(schema_version=1, positions=DEFAULT_POSITIONS, custom=False))


def register_layout_routes(app, store):
    from flask import jsonify, request

    @app.put('/api/sessions/<session_id>/layouts/<call_id>')
    def save_layout(session_id, call_id):
        call = get_call(call_id)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not {'revision', 'mutation_id', 'positions'} <= set(payload) or set(payload) - {'revision', 'mutation_id', 'positions', 'design'}:
            raise ValueError('Provide revision, mutation_id, and positions (null resets the template)')
        positions = validate_positions(payload['positions']) if payload['positions'] is not None else None
        design = validate_design(payload['design'], call) if 'design' in payload else None

        def apply(session):
            if session.get('mode') == 'historical_review':
                raise ValueError('Historical review batches cannot edit planned play designs')
            if design is not None:
                designs = session.setdefault('designs', {})
                previous = designs.get(call_id, {})
                new_positions = positions if positions is not None else DEFAULT_POSITIONS
                if previous.get('definition') != design or previous.get('positions') != new_positions:
                    designs[call_id] = dict(version=previous.get('version', 0) + 1,
                        definition=copy.deepcopy(design), positions=copy.deepcopy(new_positions),
                        updated_at=now(), source='coach_declared', review_status='Unverified planned design')
                session['preferences'] = {**session.get('preferences', default_preferences()),
                                          'personnel': design['personnel'], 'formation': design['formation']}
            layouts = session.setdefault('layouts', {})
            if positions is None or positions == DEFAULT_POSITIONS:
                layouts.pop(call_id, None)
            else:
                layouts[call_id] = dict(schema_version=1, positions=positions, custom=True, updated_at=now())
            session['_undo'] = None
        return jsonify(public_session(store.mutate(session_id, payload, 'layout:' + call_id, apply)))
