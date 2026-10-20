"""Session and playbook endpoints used by the coordinator dashboard."""

import copy
import uuid
from flask import g, jsonify, request

from .labeling import register_labeling_routes
from .plans import register_plan_routes
from .dataset import register_dataset_routes
from .layouts import register_layout_routes, call_layout
from .review import register_review_routes
from .defense import describe_defense
from .game import DEFAULT_STATE, COVERAGES, advance_play, model_situation, validate_state
from .model import compare_options
from .playbook import (PLAYBOOK, get_call, CATALOG_VERSION, PERSONNEL, FORMATIONS, OBJECTIVES,
                       default_preferences, validate_preferences)
from .suitability import suggest_concepts, exclusions, decision_snapshot
from .store import Conflict, SessionStore, public_session, now

TEAMS = sorted("ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LA LAC LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split())


def register_dashboard(app, bundle, db_path, data_dir):
    store = SessionStore(db_path)
    register_plan_routes(app, store, data_dir)
    register_review_routes(app, store, data_dir)
    register_layout_routes(app, store)
    register_dataset_routes(app, store)
    register_labeling_routes(app, store, data_dir)
    teams = bundle["teams"] if bundle else TEAMS

    def body():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object")
        return payload

    @app.errorhandler(Conflict)
    def conflict(error):
        return jsonify(error=str(error)), 409

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(KeyError)
    def missing(error):
        return jsonify(error=str(error.args[0])), 404

    @app.get("/api/meta")
    def metadata():
        return jsonify(teams=teams, coverages=COVERAGES, defaults=DEFAULT_STATE,
                       preference_defaults=default_preferences(), personnel=PERSONNEL, formations=FORMATIONS,
                       coaching_objectives=OBJECTIVES,
                       capabilities=dict(action_outcomes=bundle is not None, concept_outcomes=False,
                                         defensive_forecast=False, historical_coverage=True,
                                         conversion_probability=False, turnover_probability=False,
                                         objectives=["expected_epa"]),
                       model_id=bundle.get("model_id") if bundle else None)

    @app.get("/api/playbook")
    def playbook():
        return jsonify(plays=PLAYBOOK, version=CATALOG_VERSION, outcome_scope="No concept-specific estimates")

    @app.get("/api/sessions")
    def list_sessions():
        return jsonify(sessions=[{key: session[key] for key in ("id", "revision", "state", "status", "updated_at", "drive")}
                                 for session in store.list()])

    @app.post("/api/sessions")
    def create_session():
        payload = body()
        if "state" not in payload or set(payload) - {"state", "preferences"}:
            raise ValueError("Provide state and optional preferences to create a session")
        preferences = validate_preferences(payload.get("preferences", default_preferences()), COVERAGES)
        return jsonify(public_session(store.create(validate_state(payload["state"], teams), preferences))), 201

    @app.get("/api/sessions/<session_id>")
    def get_session(session_id):
        return jsonify(public_session(store.get(session_id)))

    def edit(session_id, new_drive=False):
        payload = body()
        if not {"revision", "mutation_id", "state"} <= set(payload) or set(payload) - {"revision", "mutation_id", "state", "preferences"}:
            raise ValueError("Provide revision, mutation_id, and state")
        state = validate_state(payload["state"], teams)
        preferences = validate_preferences(payload["preferences"], COVERAGES) if "preferences" in payload else None

        def apply(session):
            if session.get("mode") == "historical_review":
                raise ValueError("Historical labeling batches cannot be used for live game tracking")
            if not new_drive and session["status"] != "active":
                raise ValueError("Set the next possession with Start new drive")
            if not new_drive and any(state[k] != session["state"][k] for k in ("posteam", "defteam")):
                raise ValueError("Changing possession requires Start new drive")
            session.update(state=state, _undo=None)
            if preferences is not None:
                session["preferences"] = preferences
            if new_drive:
                session.update(drive=session["drive"] + 1, status="active", queue=[])

        return jsonify(public_session(store.mutate(session_id, payload, "drive" if new_drive else "edit", apply)))

    @app.patch("/api/sessions/<session_id>")
    def edit_session(session_id):
        return edit(session_id)

    @app.post("/api/sessions/<session_id>/drive")
    def new_drive(session_id):
        return edit(session_id, True)

    @app.post("/api/sessions/<session_id>/queue")
    def queue_call(session_id):
        payload = body()
        if not {"revision", "mutation_id", "call_id"} <= set(payload) or set(payload) - {"revision", "mutation_id", "call_id", "presentation"}:
            raise ValueError("Provide revision, mutation_id, and call_id")
        call = get_call(payload["call_id"])

        def apply(session):
            if session["status"] != "active":
                raise ValueError("Start a new drive before queuing a call")
            blocked = exclusions(call, session["state"], session.get("preferences", default_preferences()))
            if blocked:
                raise ValueError(" ".join(blocked))
            snapshot = decision_snapshot(session, bundle.get("model_id") if bundle else None, payload.get("presentation"))
            snapshot["diagram_layout"] = copy.deepcopy(call_layout(session, call["id"]))
            snapshot["play_design"] = copy.deepcopy(session.get('designs', {}).get(call['id']))
            session["queue"].append(dict(id=uuid.uuid4().hex, call_id=call["id"], name=call["name"],
                                         action=call["type"].lower(), drive=session["drive"], created_at=now(), decision_context=snapshot))
            session["_undo"] = None
        return jsonify(public_session(store.mutate(session_id, payload, "queue", apply)))

    @app.delete("/api/sessions/<session_id>/queue/<entry_id>")
    def remove_queued_call(session_id, entry_id):
        payload = body()
        if set(payload) != {"revision", "mutation_id"}:
            raise ValueError("Provide revision and mutation_id")

        def apply(session):
            if not any(entry["id"] == entry_id for entry in session["queue"]):
                raise KeyError("Queued call not found")
            session["queue"] = [entry for entry in session["queue"] if entry["id"] != entry_id]
            session["_undo"] = None
        return jsonify(public_session(store.mutate(session_id, payload, "remove:" + entry_id, apply)))

    @app.post("/api/sessions/<session_id>/plays")
    def record_play(session_id):
        payload = body()
        if set(payload) - {"revision", "mutation_id", "call_id", "queue_id", "outcome", "presentation"}:
            raise ValueError("Unsupported play fields")
        call = get_call(payload.get("call_id"))

        def apply(session):
            if session["status"] != "active":
                raise ValueError("This drive has ended; set the next possession first")
            outcome = payload.get("outcome")
            if isinstance(outcome, dict) and call["type"] == "RUN" and outcome.get("kind") in ("sack", "incomplete"):
                raise ValueError("Sacks and incompletions require a pass call")
            updated, status = advance_play(session["state"], outcome)
            queued_id = payload.get("queue_id")
            if queued_id and not any(entry["id"] == queued_id and entry["call_id"] == call["id"] for entry in session["queue"]):
                raise ValueError("Queued call does not match the executed play")
            snapshot = decision_snapshot(session, bundle.get("model_id") if bundle else None, payload.get("presentation"))
            snapshot["diagram_layout"] = copy.deepcopy(call_layout(session, call["id"]))
            snapshot["play_design"] = copy.deepcopy(session.get('designs', {}).get(call['id']))
            snapshot["selected_call_id"] = call["id"]
            snapshot["selected_call_exclusions"] = exclusions(call, session["state"], snapshot["preferences"])
            session["_undo"] = dict(state=copy.deepcopy(session["state"]), queue=copy.deepcopy(session["queue"]),
                                    preferences=copy.deepcopy(session.get("preferences", default_preferences())), status=session["status"])
            queued = next((entry for entry in session["queue"] if entry["id"] == queued_id), None)
            session["plays"].append(dict(id=uuid.uuid4().hex, call_id=call["id"], name=call["name"],
                                         action=call["type"].lower(), before=session["state"], after=updated,
                                         outcome=outcome, drive=session["drive"], created_at=now(), decision_context=snapshot,
                                         queued_decision_context=queued.get("decision_context") if queued else None))
            session.update(state=updated, status=status)
            session["preferences"] = {**snapshot["preferences"], "anticipated_coverage": "UNKNOWN"}
            if queued_id:
                session["queue"] = [entry for entry in session["queue"] if entry["id"] != queued_id]
        return jsonify(public_session(store.mutate(session_id, payload, "play", apply)))

    @app.post("/api/sessions/<session_id>/undo")
    def undo(session_id):
        payload = body()
        if set(payload) != {"revision", "mutation_id"}:
            raise ValueError("Provide revision and mutation_id")

        def apply(session):
            previous = session.get("_undo")
            if previous is None:
                raise Conflict("Only the latest play can be undone, before another change")
            session.update(previous)
            session["plays"].pop()
            session["_undo"] = None
        return jsonify(public_session(store.mutate(session_id, payload, "undo", apply)))

    @app.get("/api/sessions/<session_id>/evaluation")
    def evaluate_session(session_id):
        session = store.get(session_id)
        g.session_id = session_id
        g.session_revision = session["revision"]
        g.processed_situation = model_situation(session["state"])
        g.history_length = len(session["plays"])
        result = dict(session_id=session_id, revision=session["revision"], comparison=None, branches=[],
                      design_versions={key: value['version'] for key, value in session.get('designs', {}).items()},
                      design_outcomes=False,
                      outcome_input_snapshot=model_situation(session['state']),
                      situational_fit=suggest_concepts(session["state"], session.get("preferences", default_preferences())) if session["status"] == "active" else None,
                      defense=describe_defense(data_dir, session["state"]),
                      status="ready" if bundle else "model_unavailable",
                      concept_outcomes=None, conversion_probability=None, turnover_probability=None)
        if session["status"] != "active":
            result["status"] = session["status"]
        elif bundle:
            state = session["state"]
            allowed = None if state["action_filter"] == "all" else [state["action_filter"]]
            result["comparison"] = compare_options(bundle, model_situation(state), allowed)
            for label, gain in [("If you gain the first down", state["ydstogo"]), ("If the play gains no yards", 0)]:
                terminal = gain == state["yardline_100"]
                next_state, next_status = advance_play(state, dict(kind="touchdown" if terminal else "gain", yards=gain, elapsed_seconds=0))
                next_comparison = compare_options(bundle, model_situation(next_state), allowed) if next_status == "active" else None
                result["branches"].append(dict(label=label, state=next_state, status=next_status,
                                                comparison=next_comparison, assumption="What-if only; clock held constant, no probability assigned"))
        return jsonify(result)
