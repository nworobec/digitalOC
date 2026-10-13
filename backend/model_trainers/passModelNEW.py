import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

try:
    from .upload_to_release import upload_model_to_release
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from upload_to_release import upload_model_to_release

DATA_FILES = [
    "../data/merged_pass_model_data_2020.csv",
    "../data/merged_pass_model_data_2021.csv",
    "../data/merged_pass_model_data_2022.csv",
    "../data/merged_pass_model_data_2023.csv",
    "../data/merged_pass_model_data_2024.csv",
]
OUTPUT_DIR = Path("../models")
OUTPUT_DIR.mkdir(exist_ok=True)

# Post-snap execution targets for tendency scouting
TARGETS = [
    "pass_target_area",  # Composite of length + location
    "route",
    "receiver_position",
]

NUMERIC_FEATURES = [
    "down", "ydstogo", "yardline_100", "goal_to_go", "qtr",
    "quarter_seconds_remaining", "game_seconds_remaining", "score_differential",
    "posteam_timeouts_remaining", "defteam_timeouts_remaining",
    "is_redzone", "is_goal_to_go", "is_backed_up", "is_third_long",
    "is_third_short", "is_second_long", "is_first_down", "is_two_minute",
    "is_close_game_late", "is_blowout", "is_leading", "is_trailing",
    "score_margin_abs", "is_midfield_aggression", "is_deep_redzone",
    "prev_is_pass", "prev_is_run", "prev_yards_gained",
    "two_consecutive_runs", "two_consecutive_passes"
]

CATEGORICAL_FEATURES = [
    "posteam", "defteam", "offense_personnel", "offense_formation", 
    "shotgun", "no_huddle"
]

RANDOM_STATE = 42
TEST_SIZE = 0.2
MIN_SAMPLES_PER_CLASS = 15


def load_all_existing(files: List[str]) -> pd.DataFrame:
    """Load and concatenate all available historical data."""
    dfs = [pd.read_csv(f, low_memory=False) for f in files if Path(f).exists()]
    if not dfs:
        raise FileNotFoundError("No pass model data files found.")
    return pd.concat(dfs, ignore_index=True)


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive situational context and composite targets."""
    df2 = df.copy()

    # Basic safety for missing columns
    def safe_get(col, default=0):
        return df2[col] if col in df2.columns else pd.Series([default]*len(df2))

    df2["yardline_100"] = safe_get("yardline_100", 50)
    df2["goal_to_go"] = safe_get("goal_to_go", 0)
    df2["down"] = safe_get("down", 1)
    df2["ydstogo"] = safe_get("ydstogo", 10)
    df2["quarter_seconds_remaining"] = safe_get("quarter_seconds_remaining", 900)
    df2["qtr"] = safe_get("qtr", 1)
    df2["score_differential"] = safe_get("score_differential", 0)

    # Down and Distance context
    df2["is_third_long"] = ((df2["down"] == 3) & (df2["ydstogo"] >= 7)).astype(int)
    df2["is_third_short"] = ((df2["down"] == 3) & (df2["ydstogo"] <= 3)).astype(int)
    df2["is_second_long"] = ((df2["down"] == 2) & (df2["ydstogo"] >= 8)).astype(int)
    df2["is_first_down"] = (df2["down"] == 1).astype(int)

    # Field position context
    df2["is_redzone"] = (df2["yardline_100"] <= 20).astype(int)
    df2["is_goal_to_go"] = df2["goal_to_go"].fillna(0).astype(int)
    df2["is_backed_up"] = (df2["yardline_100"] >= 80).astype(int)
    df2["is_midfield_aggression"] = df2["yardline_100"].between(35, 45).astype(int)
    df2["is_deep_redzone"] = (df2["yardline_100"] <= 10).astype(int)

    # Game state context
    df2["is_two_minute"] = (df2["quarter_seconds_remaining"] <= 120).astype(int)
    df2["is_close_game_late"] = ((df2["qtr"] == 4) & (df2["score_differential"].abs() <= 8)).astype(int)
    df2["is_blowout"] = (df2["score_differential"].abs() >= 21).astype(int)
    df2["is_leading"] = (df2["score_differential"] > 0).astype(int)
    df2["is_trailing"] = (df2["score_differential"] < 0).astype(int)
    df2["score_margin_abs"] = df2["score_differential"].abs()
    df2["is_must_convert_passing_down"] = (
        (df2["down"] >= 3) & 
        (df2["ydstogo"] >= 8) & 
        (df2["is_trailing"] == 1) & 
        (df2["quarter_seconds_remaining"] <= 300)
    ).astype(int)

    # Clean categoricals
    for col in CATEGORICAL_FEATURES:
        if col in df2.columns:
            df2[col] = df2[col].fillna("UNKNOWN").astype(str)
        else:
            df2[col] = "UNKNOWN"

    # COMPOSITE TARGET CREATION
    if "pass_length" in df2.columns and "pass_location" in df2.columns:
        df2["pass_target_area"] = df2["pass_length"].astype(str) + "_" + df2["pass_location"].astype(str)
        # Clean out generic NaNs
        df2.loc[df2["pass_target_area"].str.contains("nan", na=False, case=False), "pass_target_area"] = np.nan

    return df2


def filter_rare_classes(y: pd.Series, min_samples: int = MIN_SAMPLES_PER_CLASS) -> pd.Series:
    """Group extremely rare labels into 'OTHER'."""
    counts = y.value_counts()
    rare = counts[counts < min_samples].index
    if len(rare) == 0:
        return y
    y2 = y.copy().astype(str)
    y2[y2.isin(rare)] = "OTHER"
    return y2


def prepare_target_data(df: pd.DataFrame, target: str, global_features: List[str]) -> Tuple[pd.DataFrame, pd.Series]:
    """Isolate valid rows for the specific target and apply one-hot encoding."""
    if target not in df.columns:
        raise KeyError(target)
    
    mask = df[target].notna()
    if mask.sum() == 0:
        raise ValueError(f"No valid rows for target {target}")
        
    X_raw = df.loc[mask, global_features].copy()
    y = df.loc[mask, target].copy().astype(str)
    
    y = filter_rare_classes(y)
    
    # Drop rows if 'OTHER' itself is too small to split
    counts = y.value_counts()
    if (counts < MIN_SAMPLES_PER_CLASS).any():
        keep = y.isin(counts[counts >= MIN_SAMPLES_PER_CLASS].index)
        X_raw = X_raw.loc[keep]
        y = y.loc[keep]
        
    X_encoded = pd.get_dummies(X_raw, columns=CATEGORICAL_FEATURES, drop_first=True, dtype=int)
    return X_encoded, y


def train_target_model(X: pd.DataFrame, y: pd.Series, target: str) -> Dict[str, Any]:
    print(f"\n--- Training Target: {target} ---")
    print(f"Samples: {len(y)} | Classes: {len(y.unique())}")
    
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
    
    # No artificial class weights; unweighted gives calibrated probability priors
    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=None,
        min_samples_leaf=2,
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )
    
    start = time.time()
    clf.fit(X_train, y_train)
    elapsed = time.time() - start
    
    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"Accuracy ({target}): {acc:.3f} | Train time: {elapsed:.1f}s")
    
    return {
        "model": clf,
        "accuracy": float(acc),
        "train_time_s": elapsed,
        "classes": clf.classes_.tolist(),
        "feature_columns": X_train.columns.tolist(),
    }


def train_pass_models() -> Dict[str, Dict[str, Any]]:
    start = time.time()
    print("=== Training Pass Tendency Models ===")
    
    df = load_all_existing(DATA_FILES)
    if "play_type" in df.columns:
        df = df[df["play_type"] == "pass"].copy()
        
    df = add_derived_features(df)
    models_info = {}
    
    global_features = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    available_features = [f for f in global_features if f in df.columns]
    
    for target in TARGETS:
        try:
            X, y = prepare_target_data(df, target, available_features)
            if X.empty or y.nunique() < 2:
                print(f"Skipping {target}: insufficient cleaned data")
                continue
            
            info = train_target_model(X, y, target)
            models_info[target] = info
        except Exception as e:
            print(f"Failed to train {target}: {e}")
            
    print(f"\nTotal training time: {(time.time() - start)/60:.2f} minutes")
    return models_info


def predict_pass_metrics(situation_dict: Dict[str, Any], trained_models: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Outputs probability distributions over pass targets and routes for tendency scouting.
    """
    situation_df = pd.DataFrame([situation_dict])
    situation_df = add_derived_features(situation_df)
    
    # Single-row encoding must retain categories; reindex below applies the
    # training schema, including its omitted baseline and unseen categories.
    situation_encoded = pd.get_dummies(
        situation_df, columns=CATEGORICAL_FEATURES, drop_first=False, dtype=int
    )
    
    predictions = {}
    for target, model_info in trained_models.items():
        model = model_info['model']
        model_features = model_info['feature_columns']
        classes = model_info['classes']
        
        # Align inference columns to training schema
        X_infer = situation_encoded.reindex(columns=model_features, fill_value=0)
        
        # Get probability distribution
        probs = model.predict_proba(X_infer)[0]
        
        # Get top 3 most likely outcomes
        top_indices = np.argsort(probs)[::-1][:3]
        
        predictions[target] = [
            {"label": classes[idx], "probability": round(float(probs[idx]), 3)}
            for idx in top_indices
        ]
        
    return predictions


if __name__ == "__main__":
    trained_pass_models = train_pass_models()
    upload_model_to_release(trained_pass_models, "pass_model.joblib", "pass-model")
