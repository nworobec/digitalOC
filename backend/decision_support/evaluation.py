"""Read-only session evaluation shared by the dashboard and assistant."""

from .defense import describe_defense
from .game import advance_play, model_situation
from .model import compare_options
from .playbook import default_preferences
from .suitability import suggest_concepts


def evaluate_session(session, bundle, data_dir, compare=compare_options):
    result = dict(session_id=session["id"], revision=session["revision"], comparison=None, branches=[],
                  design_versions={key: value["version"] for key, value in session.get("designs", {}).items()},
                  design_outcomes=False,
                  outcome_input_snapshot=model_situation(session["state"]),
                  situational_fit=suggest_concepts(session["state"], session.get("preferences", default_preferences()))
                  if session["status"] == "active" else None,
                  defense=describe_defense(data_dir, session["state"]),
                  status="ready" if bundle else "model_unavailable",
                  concept_outcomes=None, conversion_probability=None, turnover_probability=None)
    if session["status"] != "active":
        result["status"] = session["status"]
    elif bundle:
        state = session["state"]
        allowed = None if state["action_filter"] == "all" else [state["action_filter"]]
        result["comparison"] = compare(bundle, model_situation(state), allowed)
        for label, gain in [("If you gain the first down", state["ydstogo"]),
                            ("If the play gains no yards", 0)]:
            terminal = gain == state["yardline_100"]
            next_state, next_status = advance_play(
                state, dict(kind="touchdown" if terminal else "gain", yards=gain, elapsed_seconds=0))
            next_comparison = compare(bundle, model_situation(next_state), allowed) if next_status == "active" else None
            result["branches"].append(dict(
                label=label, state=next_state, status=next_status, comparison=next_comparison,
                assumption="What-if only; clock held constant, no probability assigned"))
    return result
