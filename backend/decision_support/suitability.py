"""Deterministic, provisional coaching rules, never concept outcome predictions."""

from .playbook import PLAYBOOK, CATALOG_VERSION, default_preferences

RULE_VERSION = "situational-fit-1"


def exclusions(call, state, preferences):
    reasons = []
    if call["id"] not in preferences["installed_call_ids"]:
        reasons.append("Not in your available playbook.")
    if state["action_filter"] != "all" and call["type"].lower() != state["action_filter"]:
        reasons.append("Excluded by your run/pass constraint.")
    if preferences["personnel"] != "any" and preferences["personnel"] not in call["personnel"]:
        reasons.append("This template does not match the selected personnel.")
    if preferences["formation"] != "any" and preferences["formation"] not in call["formations"]:
        reasons.append("This template does not match the selected formation.")
    if state["yardline_100"] < call["minimum_field_space"]:
        reasons.append(f"This template requires at least {call['minimum_field_space']} yards to the goal line.")
    return reasons


def suggest_concepts(state, preferences=None):
    preferences = preferences or default_preferences()
    eligible, excluded = [], []
    for call in PLAYBOOK:
        blocked = exclusions(call, state, preferences)
        if blocked:
            excluded.append(dict(call_id=call["id"], name=call["name"], reasons=blocked))
            continue
        points, reasons, cautions = 0, [], []
        low, high = call["distance_range"]
        if low <= state["ydstogo"] <= high:
            points += 4
            reasons.append(f"Fits this template's {low}–{high} yard distance band.")
        else:
            cautions.append(f"Outside this template's preferred {low}–{high} yard distance band.")
        coverage = preferences["anticipated_coverage"]
        if coverage != "UNKNOWN" and coverage in call["preferred_coverages"]:
            points += 3
            reasons.append(f"Tagged for your anticipated {coverage.replace('_', ' ')} look; confirm after the snap.")
        if preferences["objective"] in call["goals"]:
            points += 3
            reasons.append({"clock": "Matches your use-clock preference; no clock or win-probability estimate is available.",
                            "conversion": "Tagged for your move-the-chains preference; conversion probability is unavailable.",
                            "explosive": "Tagged for your explosive-play preference; explosive-play probability is unavailable."}[preferences["objective"]])
        if state["down"] >= 3 and state["ydstogo"] <= 3 and "conversion" in call["goals"]:
            points += 2
            reasons.append("Tagged for a short-yardage conversion situation.")
        if state["down"] >= 3 and state["ydstogo"] >= 7 and call["type"] == "PASS" and low <= state["ydstogo"] <= high:
            points += 2
            reasons.append("Long yardage on a later down: the rules favor distance-compatible passing templates.")
        if state["yardline_100"] <= 10 and call["id"] in ("power", "zone", "slant_flat", "stick", "sprint_out"):
            points += 2
            reasons.append("Uses a compact-field starter template.")
        if preferences["objective"] == "balanced" and state["qtr"] == 4 and state["quarter_seconds_remaining"] <= 120:
            if state["offense_score"] > state["defense_score"] and call["type"] == "RUN":
                points += 2
                reasons.append("Late lead: the balanced rules give runs a modest clock-use preference.")
            elif state["offense_score"] < state["defense_score"] and call["type"] == "PASS":
                points += 2
                reasons.append("Late deficit: the balanced rules give passes a modest preference.")
        if preferences["personnel"] != "any":
            reasons.append(f"Compatible with {preferences['personnel']} personnel.")
        if not reasons:
            reasons.append("Meets your availability, personnel, formation, and field-space constraints.")
        if state["down"] == 4:
            cautions.append("Kicking alternatives are outside this shortlist.")
        eligible.append((points, dict(call_id=call["id"], name=call["name"], reasons=reasons, cautions=cautions)))
    eligible.sort(key=lambda item: (-item[0], item[1]["call_id"]))
    return dict(rule_version=RULE_VERSION, catalog_version=CATALOG_VERSION, basis="provisional_coaching_rules",
                suggestions=[item[1] for item in eligible[:3]], eligible_call_ids=[item[1]["call_id"] for item in eligible],
                excluded=excluded, review_status="Requires review against your team's installed playbook",
                limitations="Situational fit only. No concept EPA, success probability, or calibrated defensive forecast.")


def decision_snapshot(session, model_id, presentation=None):
    preferences = session.get("preferences", default_preferences())
    fit = suggest_concepts(session["state"], preferences)
    ids = [item["call_id"] for item in fit["suggestions"]]
    if presentation is not None:
        if (not isinstance(presentation, dict) or set(presentation) != {"revision", "candidate_ids"}
                or type(presentation["revision"]) is not int or presentation["revision"] != session["revision"]
                or presentation["candidate_ids"] != ids):
            raise ValueError("Displayed suggestions are stale; refresh before recording")
    return dict(session_revision=session["revision"], preferences=preferences, situation=session["state"],
                rule_version=RULE_VERSION, catalog_version=CATALOG_VERSION, outcome_model_id=model_id,
                suggestions=fit["suggestions"], eligible_call_ids=fit["eligible_call_ids"],
                displayed_candidate_ids=ids if presentation is not None else None,
                display_source="client_reported" if presentation is not None else "not_reported")
