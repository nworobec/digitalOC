"""Evidence-backed, deterministic coaching drafts. No learned sequence claims."""

import copy
import hashlib
import json
from flask import jsonify, request
from .defense import describe_defense
from .playbook import CATALOG_VERSION, default_preferences, get_call
from .store import Conflict, now, public_session
from .suitability import suggest_concepts


def context(session):
    return dict(state=session['state'], preferences=session.get('preferences', default_preferences()),
                catalog_version=CATALOG_VERSION, **({'designs': session['designs']} if session.get('designs') else {}))


def context_id(session):
    return hashlib.sha256(json.dumps(context(session), sort_keys=True).encode()).hexdigest()


def draft_plan(session, defense):
    fit = suggest_concepts(session['state'], session.get('preferences', default_preferences()))
    calls = [get_call(call_id) for call_id in fit['eligible_call_ids']]
    historical = defense.get('status') == 'historical_frequencies'
    top = defense['distribution'][0]['coverage'] if historical and defense.get('distribution') else None
    counters = []
    # Coverage tags are catalog coaching hypotheses, not estimated response values.
    for call in calls:
        if top and top in call['preferred_coverages']:
            counters.append(dict(call_id=call['id'], condition=f'If the defense shows {top.replace("_", " ")} and protection is confirmed',
                                 reason=f'Catalog coverage tag: {top}. {call["read"]}'))
    for call in calls[:3]:
        for related in call['counters']:
            if related in fit['eligible_call_ids'] and len(counters) < 5:
                counters.append(dict(call_id=related, condition=f'If {call["name"]} is taken away and the new look fits this alternative',
                                     reason=f'Related concept in the {call["name"]} template; confirm assignments before calling.'))
                break
    state = session['state']
    design_note = (' Custom designs are saved for this game. Review their route, blocking, motion, and alignment changes against each template before using this script.'
                   if session.get('designs') else '')
    return dict(title=f'{state["posteam"]} vs {state["defteam"]} game plan',
                notes=f'Objective: {session.get("preferences", default_preferences())["objective"]}. Start from down {state["down"]} and {state["ydstogo"]} yards to go. '
                      'Use this opening script as a review order; reassess down, distance, field space, and personnel after every snap.' + design_note,
                opening_script=[dict(call_id=call['id'], purpose=call['summary'], watch=call['read']) for call in calls[:5]],
                counters=counters[:5])


def validate_content(content, session):
    if not isinstance(content, dict) or set(content) != {'title', 'notes', 'opening_script', 'counters'}:
        raise ValueError('Provide title, notes, opening_script, and counters')
    def text(value, limit):
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f'Plan text must be a string of at most {limit} characters')
    text(content['title'], 160)
    text(content['notes'], 6000)
    eligible = suggest_concepts(session['state'], session.get('preferences', default_preferences()))['eligible_call_ids']
    for key, fields in [('opening_script', {'call_id', 'purpose', 'watch'}), ('counters', {'call_id', 'condition', 'reason'})]:
        rows = content[key]
        if not isinstance(rows, list) or len(rows) > 15:
            raise ValueError('Use at most 15 entries per section')
        for row in rows:
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError('Invalid plan entry fields')
            if row['call_id'] not in eligible:
                raise ValueError('Plan calls must match the current available playbook and situation; regenerate or remove unavailable calls')
            for field in fields - {'call_id'}:
                text(row[field], 1200)
    return copy.deepcopy(content)


def register_plan_routes(app, store, data_dir):
    @app.post('/api/sessions/<session_id>/plan/generate')
    def generate_plan(session_id):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) != {'revision', 'mutation_id'}:
            raise ValueError('Provide revision and mutation_id')
        # Load coverage outside the SQLite write transaction.
        initial = store.get(session_id)
        defense = describe_defense(data_dir, initial['state'])
        def apply(session):
            if session.get('mode') == 'historical_review':
                raise ValueError('Create a live game session to draft a plan')
            session['coaching_plan'] = dict(version='coaching-plan-1', engine='coaching_rules',
                generated_at=now(), updated_at=now(), edited_by_coach=False,
                context_id=context_id(session), context=copy.deepcopy(context(session)),
                evidence=defense, content=draft_plan(session, defense))
            session['_undo'] = None
        return jsonify(public_session(store.mutate(session_id, payload, 'generate_plan', apply)))

    @app.put('/api/sessions/<session_id>/plan')
    def save_plan(session_id):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) != {'revision', 'mutation_id', 'context_id', 'content'}:
            raise ValueError('Provide revision, mutation_id, context_id, and content')
        def apply(session):
            plan = session.get('coaching_plan')
            if not plan or payload['context_id'] != plan['context_id']:
                raise Conflict('The plan changed. Reload the saved plan before editing.')
            if plan['context_id'] != context_id(session):
                raise Conflict('The situation or playbook changed. Regenerate the plan before saving.')
            plan.update(content=validate_content(payload['content'], session), edited_by_coach=True, updated_at=now())
            session['_undo'] = None
        return jsonify(public_session(store.mutate(session_id, payload, 'save_plan', apply)))
