"""Validated manual game state and deterministic scrimmage-play transitions."""

import math
from .data import FEATURES
from .model import validate_situation

DEFAULT_STATE = dict(posteam="KC", defteam="BUF", offense_score=0, defense_score=0,
                     qtr=1, quarter_seconds_remaining=900, down=1, ydstogo=10,
                     yardline_100=75, posteam_timeouts_remaining=3,
                     defteam_timeouts_remaining=3, coverage="UNKNOWN", action_filter="all")
COVERAGES = ["UNKNOWN", "MAN", "ZONE", "COVER_0", "COVER_1", "COVER_2", "2_MAN", "COVER_3", "COVER_4", "COVER_6"]


def integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or int(value) != value or not low <= value <= high:
        raise ValueError(f"{name} must be an integer between {low} and {high}")
    return int(value)


def model_situation(state):
    values = {**state, "game_seconds_remaining": (4 - state["qtr"]) * 900 + state["quarter_seconds_remaining"],
              "score_differential": state["offense_score"] - state["defense_score"]}
    return {key: values[key] for key in FEATURES}


def validate_state(data, teams):
    if not isinstance(data, dict) or set(data) != set(DEFAULT_STATE):
        raise ValueError("Provide the complete game state with the documented fields")
    state = dict(data)
    for key, low, high in [("offense_score", 0, 100), ("defense_score", 0, 100),
                           ("qtr", 1, 4), ("quarter_seconds_remaining", 1, 900),
                           ("down", 1, 4), ("ydstogo", 1, 99), ("yardline_100", 1, 99),
                           ("posteam_timeouts_remaining", 0, 3), ("defteam_timeouts_remaining", 0, 3)]:
        state[key] = integer(state[key], key, low, high)
    if state["ydstogo"] > state["yardline_100"]:
        raise ValueError("Yards to go cannot exceed the distance to the opponent's goal line")
    if state["coverage"] not in COVERAGES or state["action_filter"] not in ("all", "run", "pass"):
        raise ValueError("Unsupported coverage observation or action filter")
    normalized = validate_situation(model_situation(state), teams)
    state["posteam"] = normalized.posteam.iloc[0]
    state["defteam"] = normalized.defteam.iloc[0]
    return state


def advance_play(state, outcome):
    """TDs/turnovers stop the drive; the OC explicitly sets the next possession.

    No inferred return yards, PATs, kicks, penalties, or overtime rules.
    """
    if not isinstance(outcome, dict) or set(outcome) - {"kind", "yards", "elapsed_seconds", "observed_coverage"}:
        raise ValueError("Unsupported play outcome fields")
    kind = outcome.get("kind")
    if kind not in ("gain", "incomplete", "sack", "turnover", "touchdown", "safety"):
        raise ValueError("Choose gain, incomplete, sack, turnover, touchdown, or safety")
    yards = integer(outcome.get("yards"), "yards", -99, 99)
    elapsed = integer(outcome.get("elapsed_seconds"), "elapsed_seconds", 0, state["quarter_seconds_remaining"])
    coverage = outcome.get("observed_coverage", "UNKNOWN")
    if coverage not in COVERAGES:
        raise ValueError("Unsupported observed coverage")
    if kind == "incomplete" and yards != 0:
        raise ValueError("An incomplete pass must have zero yards")
    if kind == "sack" and yards > 0:
        raise ValueError("A sack cannot gain yards")
    field = state["yardline_100"] - yards
    if not 0 <= field <= 100:
        raise ValueError("Yardage would move beyond the goal line; enter yards to the goal line")
    if kind == "touchdown" and field != 0:
        raise ValueError("Touchdown yardage must reach the opponent's goal line")
    if kind == "safety" and field != 100:
        raise ValueError("Safety yardage must reach your own goal line")
    if field in (0, 100) and kind not in ("touchdown", "safety", "turnover"):
        raise ValueError("Select touchdown or safety when the play reaches a goal line")
    updated = {**state, "yardline_100": field, "coverage": "UNKNOWN"}
    status = "active"
    if kind == "touchdown":
        updated["offense_score"] += 6
        status = "awaiting_drive"
    elif kind == "safety":
        updated["defense_score"] += 2
        status = "awaiting_drive"
    elif kind == "turnover":
        status = "awaiting_drive"
    elif yards >= state["ydstogo"]:
        updated.update(down=1, ydstogo=min(10, field))
    elif state["down"] == 4:
        status = "awaiting_drive"
    else:
        updated.update(down=state["down"] + 1, ydstogo=state["ydstogo"] - yards)
    clock = state["quarter_seconds_remaining"] - elapsed
    if clock == 0 and state["qtr"] < 4:
        updated.update(qtr=state["qtr"] + 1, quarter_seconds_remaining=900)
        if state["qtr"] == 2:
            updated.update(posteam_timeouts_remaining=3, defteam_timeouts_remaining=3)
            status = "awaiting_drive"
    elif clock == 0:
        updated["quarter_seconds_remaining"] = 0
        status = "finished"
    else:
        updated["quarter_seconds_remaining"] = clock
    if max(updated["offense_score"], updated["defense_score"]) > 100:
        raise ValueError("Score exceeds the supported range")
    return updated, status
