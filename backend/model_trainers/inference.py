"""Compatibility helpers for the existing dummy-column model artifacts."""

import pandas as pd
from flask import g, has_request_context


def encode_inference(frame, categorical_columns=None):
    """Retain the observed category; align later to the saved training columns.

    Dropping the first category of a one-row request removes every category.
    Encoding all categories then selecting saved columns also correctly handles
    the reference categories omitted during training.
    """
    frame = frame.copy()
    for name in ("posteam", "defteam"):
        if name in frame:
            frame[name] = frame[name].replace({"LAR": "LA", "OAK": "LV", "SD": "LAC"})
    return pd.get_dummies(frame, columns=categorical_columns, drop_first=False)


def align_inference(frame, columns, model_name):
    aligned = frame.reindex(columns=list(columns), fill_value=0)
    if has_request_context():
        summaries = getattr(g, "model_inputs", [])
        summaries.append({
            "model": model_name,
            "feature_count": len(aligned.columns),
            "active_categories": [str(c) for c in aligned.columns
                                  if str(c).startswith(("posteam_", "defteam_", "defense_coverage_type_"))
                                  and bool(aligned[c].iloc[0])],
            "numeric_inputs": {str(c): float(aligned[c].iloc[0]) for c in aligned.columns
                               if c in ("down", "ydstogo", "yardline_100", "qtr", "game_seconds_remaining",
                                        "prev_yards_gained", "prev_is_run", "prev_is_pass")},
        })
        g.model_inputs = summaries
    return aligned
