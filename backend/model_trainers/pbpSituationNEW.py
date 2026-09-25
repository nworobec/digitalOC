import io
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, brier_score_loss, classification_report
from sklearn.model_selection import train_test_split
from sklearn.calibration import CalibratedClassifierCV

try:
    from .add_additional_pbp_features import add_additional_pbp_features
    from .upload_to_release import upload_model_to_release
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from add_additional_pbp_features import add_additional_pbp_features
    from upload_to_release import upload_model_to_release

PBP_FILES = ["../data/pbp_2024_0.csv", "../data/pbp_2024_1.csv"]
PARTICIPATION_FILE = "../data/pbp_participation_2024.csv"
METADATA_PATH = Path(__file__).parent / "pbp_situation_features.json"

NUMERIC_FEATURES = [
    "down",
    "ydstogo",
    "yardline_100",
    "goal_to_go",
    "quarter_seconds_remaining",
    "half_seconds_remaining",
    "game_seconds_remaining",
    "score_differential",
    "posteam_timeouts_remaining",
    "defteam_timeouts_remaining",
    "is_redzone",
    "is_deep_redzone",
    "is_midfield_aggression",
    "is_two_minute",
    "prev_is_pass",
    "prev_is_run",
    "prev_yards_gained",
    "two_consecutive_runs",
    "two_consecutive_passes",
    "is_obvious_passing_down",  # <-- NEW
    "is_desperation_time",      # <-- NEW
]

CATEGORICAL_FEATURES = [ #removed teams due to emptyness of one-hot encoding
    "offense_personnel",
    "offense_formation",
]


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    df_out = df.copy()

    # Infer quarter if missing (required for API inference)
    if "qtr" not in df_out.columns:
        def infer_qtr(sec):
            if pd.isna(sec) or sec > 2700: return 1
            if sec > 1800: return 2
            if sec > 900: return 3
            return 4
        df_out["qtr"] = df_out["game_seconds_remaining"].apply(infer_qtr)

    # Field position flags
    df_out["is_redzone"] = (df_out["yardline_100"] <= 20).astype(int)
    df_out["is_deep_redzone"] = (df_out["yardline_100"] <= 10).astype(int)
    df_out["is_midfield_aggression"] = df_out["yardline_100"].between(35, 45).astype(int)
    df_out["is_two_minute"] = (df_out["quarter_seconds_remaining"] <= 120).astype(int)

    # High-leverage passing flags
    df_out["is_obvious_passing_down"] = (
        ((df_out["down"] == 3) & (df_out["ydstogo"] >= 6)) | 
        ((df_out["down"] == 4) & (df_out["ydstogo"] >= 4))
    ).astype(int)
    
    df_out["is_desperation_time"] = (
        (df_out["score_differential"] < -8) & 
        (df_out["quarter_seconds_remaining"] <= 900) & 
        (df_out["qtr"].isin([3, 4]))
    ).astype(int)

    # Clean missing categorical values
    for col in CATEGORICAL_FEATURES:
        if col in df_out.columns:
            df_out[col] = df_out[col].fillna("UNKNOWN").astype(str)
        else:
            df_out[col] = "UNKNOWN"

    return df_out


def train_pbp_model() -> Tuple[RandomForestClassifier, List[str]]:
    dfs = [pd.read_csv(f, low_memory=False) for f in PBP_FILES if Path(f).exists()]
    if not dfs:
        raise FileNotFoundError("Play-by-play data files not found.")
    df = pd.concat(dfs, ignore_index=True)
    df = add_additional_pbp_features(df)

    if Path(PARTICIPATION_FILE).exists():
        part_df = pd.read_csv(PARTICIPATION_FILE, low_memory=False)
        part_df = part_df.rename(columns={"nflverse_game_id": "game_id"})
        merge_cols = ["game_id", "play_id", "offense_personnel", "offense_formation"]
        avail_merge_cols = [c for c in merge_cols if c in part_df.columns]
        df = pd.merge(df, part_df[avail_merge_cols], on=["game_id", "play_id"], how="left")

    # 1. Filter out QBs kneeling or spiking to prevent late-game clock biases
    df_filtered = df[
        df["play_type"].isin(["run", "pass"]) & 
        (df["score_differential"].abs() <= 16) &
        (df.get("qb_kneel", 0) == 0) &
        (df.get("qb_spike", 0) == 0)
    ].copy()

    # 2. Bulletproof pass intent 
    df_filtered["is_pass_intent"] = (
        (df_filtered["play_type"] == "pass") | 
        (df_filtered.get("qb_scramble", 0) == 1)
    ).astype(int)
    
    df_filtered = add_derived_features(df_filtered)

    feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    X = df_filtered[feature_cols].copy()
    y = df_filtered["is_pass_intent"].copy()

    # 3. Fill missing numeric data with 0 BEFORE dropping, saving thousands of plays
    for col in NUMERIC_FEATURES:
        if col in X.columns:
            X[col] = X[col].fillna(0)

    X_encoded = pd.get_dummies(X, columns=CATEGORICAL_FEATURES, drop_first=True, dtype=int)
    trained_columns = X_encoded.columns.tolist()

    X_train, X_test, y_train, y_test = train_test_split(
        X_encoded, y, test_size=0.2, random_state=42, stratify=y
    )

    # 4. Clean stray categoricals only
    X_train_clean = X_train.dropna()
    y_train_clean = y_train.loc[X_train_clean.index]

    # 5. Let the tree isolate 3rd & long edge cases
    model = RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_leaf=5,
        class_weight=None,
        n_jobs=-1,
        random_state=42,
    )
    model.fit(X_train_clean, y_train_clean)

    return model, trained_columns


def predict_play(situation_dict: Dict[str, Any], trained_model, feature_columns: List[str]) -> Dict[str, Any]:
    """
    Predicts situational tendency probabilities for defensive scouting.
    
    Accepts situation_dict containing situational and pre-snap features:
      - down, ydstogo, yardline_100, goal_to_go
      - quarter_seconds_remaining, half_seconds_remaining, game_seconds_remaining
      - score_differential, posteam_timeouts_remaining, defteam_timeouts_remaining
      - posteam, defteam, offense_personnel, offense_formation
      - prev_is_pass, prev_is_run, prev_yards_gained, two_consecutive_runs, two_consecutive_passes
    """
    situation_df = pd.DataFrame([situation_dict])
    situation_df = add_derived_features(situation_df)

    # One-hot encode and reindex to match the training feature schema
    situation_encoded = pd.get_dummies(situation_df, columns=CATEGORICAL_FEATURES, drop_first=True, dtype=int)
    situation_encoded = situation_encoded.reindex(columns=feature_columns, fill_value=0)

    # Extract calibrated probabilities
    probabilities = trained_model.predict_proba(situation_encoded)[0]
    classes = list(trained_model.classes_)
    
    pass_prob = float(probabilities[classes.index(1)])
    run_prob = float(probabilities[classes.index(0)])

    primary_tendency = "PASS" if pass_prob >= 0.50 else "RUN"

    report = {
        "primary_tendency": primary_tendency,
        "pass_probability": round(pass_prob, 3),
        "run_probability": round(run_prob, 3),
        "confidence_delta": round(abs(pass_prob - run_prob), 3),
    }

    print(f"Tendency: {primary_tendency} | Pass Prob: {pass_prob:.1%} | Run Prob: {run_prob:.1%}")
    return report


if __name__ == "__main__":
    model, feature_columns = train_pbp_model()

    # Save feature columns locally for inference consistency
    with open(METADATA_PATH, "w") as f:
        json.dump({"feature_columns": feature_columns, "model_type": "RandomForestClassifier"}, f, indent=2)
    print(f"Saved feature metadata to {METADATA_PATH}")

    # Upload trained model artifact
    upload_model_to_release(model, "pbp_situation_model.joblib", "pbp-model")
