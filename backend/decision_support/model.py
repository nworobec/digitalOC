"""Separate historical call likelihood from estimated action outcomes."""

import math

import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer, TransformedTargetRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .data import FEATURES, NUMERIC_FEATURES, CATEGORICAL_FEATURES, TARGETS, normalize_teams

SCHEMA_VERSION = 1
LIMITS = {
    "down": (1, 4), "ydstogo": (1, 100), "yardline_100": (1, 99),
    "qtr": (1, 4), "game_seconds_remaining": (1, 3600),
    "score_differential": (-100, 100),
    "posteam_timeouts_remaining": (0, 3), "defteam_timeouts_remaining": (0, 3),
}


def pipeline(estimator):
    # Fit once, save together, then transform all batches with the same vocabulary.
    return Pipeline([
        ("features", ColumnTransformer([
            ("numeric", "passthrough", NUMERIC_FEATURES),
            ("teams", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ])),
        ("model", estimator),
    ])


def support_key(down, distance):
    bucket = "1-3" if distance <= 3 else "4-6" if distance <= 6 else "7-10" if distance <= 10 else "11+"
    return f"{int(down)}:{bucket}"


def fit_bundle(train, *, n_estimators=60, min_samples_leaf=40):
    if set(train.action.unique()) != {"run", "pass"}:
        raise ValueError("Training requires both run and pass observations")
    params = dict(n_estimators=n_estimators, min_samples_leaf=min_samples_leaf,
                  max_depth=12, random_state=42, n_jobs=2)
    tendency = pipeline(RandomForestClassifier(**params))
    tendency.fit(train[FEATURES], train.action)
    outcomes, means, support = {}, {}, {}
    for action in ("run", "pass"):
        rows = train.loc[train.action.eq(action)]
        # Standardizing targets prevents yardage scale dominating the joint fit.
        outcomes[action] = pipeline(TransformedTargetRegressor(
            regressor=RandomForestRegressor(**params), transformer=StandardScaler(),
        ))
        outcomes[action].fit(rows[FEATURES], rows[TARGETS])
        means[action] = rows[TARGETS].mean().to_numpy()
        keys = [support_key(d, y) for d, y in zip(rows.down, rows.ydstogo)]
        support[action] = pd.Series(keys).value_counts().to_dict()
    return {
        "schema_version": SCHEMA_VERSION, "status": "experimental",
        "sklearn_version": sklearn.__version__, "features": FEATURES, "targets": TARGETS,
        "target_units": {"epa": "points", "yards_gained": "yards"},
        "train_seasons": sorted(int(x) for x in train.season.unique()),
        "teams": sorted(set(train.posteam) | set(train.defteam)),
        "tendency": tendency, "outcomes": outcomes, "action_means": means,
        "action_priors": train.action.value_counts(normalize=True).to_dict(),
        "support": support,
    }


def validate_situation(situation, teams):
    if not isinstance(situation, dict):
        raise ValueError("current_situation must be an object")
    missing = sorted(set(FEATURES) - set(situation))
    if missing:
        raise ValueError(f"Missing situation fields: {missing}")
    extra = sorted(set(situation) - set(FEATURES))
    if extra:
        raise ValueError(f"Unsupported situation fields: {extra}; this baseline uses game state and teams only")
    cleaned = {}
    for key, (low, high) in LIMITS.items():
        value = situation[key]
        if isinstance(value, bool):
            raise ValueError(f"{key} must be an integer from {low} to {high}")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be an integer from {low} to {high}") from None
        if not math.isfinite(number) or not number.is_integer() or not low <= number <= high:
            raise ValueError(f"{key} must be an integer from {low} to {high}")
        cleaned[key] = int(number)
    lower_clock = (4 - cleaned["qtr"]) * 900
    if not lower_clock <= cleaned["game_seconds_remaining"] <= lower_clock + 900:
        raise ValueError("qtr and game_seconds_remaining disagree")
    for key in CATEGORICAL_FEATURES:
        if not isinstance(situation[key], str):
            raise ValueError(f"{key} must be a team abbreviation")
        cleaned[key] = situation[key]
    frame = normalize_teams(pd.DataFrame([cleaned], columns=FEATURES))
    if frame.posteam.iloc[0] == frame.defteam.iloc[0]:
        raise ValueError("Offense and defense must be different teams")
    for key in CATEGORICAL_FEATURES:
        if frame[key].iloc[0] not in teams:
            raise ValueError(f"Unsupported {key}: {frame[key].iloc[0]}")
    return frame


def compare_options(bundle, situation, allowed_actions=None):
    if bundle.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported model schema")
    frame = validate_situation(situation, bundle["teams"])
    actions = ["run", "pass"] if allowed_actions is None else allowed_actions
    if not isinstance(actions, list) or not actions or any(a not in ("run", "pass") for a in actions):
        raise ValueError("allowed_actions must be a nonempty list containing run and/or pass")
    actions = list(dict.fromkeys(actions))
    probabilities = bundle["tendency"].predict_proba(frame)[0]
    likelihood = dict(zip(bundle["tendency"].classes_, probabilities))
    key = support_key(frame.down.iloc[0], frame.ydstogo.iloc[0])
    options = []
    for action in actions:
        epa, yards = bundle["outcomes"][action].predict(frame)[0]
        count = int(bundle["support"][action].get(key, 0))
        options.append({
            "action": action,
            "expected_epa": float(epa), "expected_yards": float(yards),
            "historical_call_probability": float(likelihood[action]),
            "training_examples_in_down_distance_bucket": count,
            "support_status": "sparse" if count < 30 else "coarse_support_only",
        })
    options.sort(key=lambda option: option["expected_epa"], reverse=True)
    for rank, option in enumerate(options, 1):
        option["estimated_rank"] = rank
    return {
        "schema_version": SCHEMA_VERSION, "status": "experimental",
        "model_id": bundle.get("model_id", "local-unversioned"),
        "target_units": bundle["target_units"],
        "ranking_metric": "expected_epa", "options": options,
        "train_seasons": bundle["train_seasons"],
        "limitations": [
            "Run/pass comparison only; no named concepts or defensive-response forecast yet.",
            "Historical call probability is not success probability and is not yet calibrated.",
            "Outcome estimates are observational, not proven benefits of changing the call.",
            "Support counts cover league-wide down/distance buckets, not this exact matchup.",
            "No validated uncertainty intervals; estimated ordering is provisional.",
            "Scope: regulation run/pass snaps; excludes kneels, spikes, nullified plays and kicking choices.",
        ],
    }
