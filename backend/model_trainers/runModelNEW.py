import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

try:
    from .upload_to_release import upload_model_to_release
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from upload_to_release import upload_model_to_release

DATA_FILES = [
    "../data/pbp_2024_0.csv",
    "../data/pbp_2024_1.csv"
]
PARTICIPATION_FILE = "../data/pbp_participation_2024.csv"

# Pre-snap features
NUMERIC_FEATURES = [
    "down", "ydstogo", "yardline_100", "goal_to_go", "qtr",
    "quarter_seconds_remaining", "half_seconds_remaining", "game_seconds_remaining", "score_differential",
    "posteam_timeouts_remaining", "defteam_timeouts_remaining",
    "is_redzone", "is_goal_line", "is_short_yardage", "is_two_minute_drill",
    "is_close_game_late", "is_midfield_aggression", "is_deep_redzone",
    "prev_is_pass", "prev_is_run", "prev_yards_gained", 
    "two_consecutive_runs", "two_consecutive_passes"
]

CATEGORICAL_FEATURES = [
    "posteam", "defteam", "offense_personnel", "offense_formation", 
    "roof", "surface", "shotgun", "no_huddle"
]

TARGETS = ["run_lane"]
MIN_SAMPLES_PER_CLASS = 15
TEST_SIZE = 0.2
RANDOM_STATE = 42


def load_data() -> pd.DataFrame:
    dfs = [pd.read_csv(f, low_memory=False) for f in DATA_FILES if Path(f).exists()]
    if not dfs:
        raise FileNotFoundError("Run model data files not found.")
    df = pd.concat(dfs, ignore_index=True)
    
    # Filter for designed runs; strictly exclude scrambles
    if "play_type" in df.columns:
        df = df[(df["play_type"] == "run") & (df.get("qb_scramble", 0) == 0)].copy()

    # Merge participation for true pre-snap context
    if Path(PARTICIPATION_FILE).exists():
        part_df = pd.read_csv(PARTICIPATION_FILE, low_memory=False)
        if "nflverse_game_id" in part_df.columns:
            part_df = part_df.rename(columns={"nflverse_game_id": "game_id"})
        elif "old_game_id" in df.columns and "old_game_id" in part_df.columns:
            part_df = part_df.rename(columns={"old_game_id": "game_id"})
            
        merge_cols = ["game_id", "play_id", "offense_personnel", "offense_formation"]
        avail_cols = [c for c in merge_cols if c in part_df.columns]
        df = pd.merge(df, part_df[avail_cols], on=["game_id", "play_id"], how="left")
        
    return df


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    
    def safe_get(col, default=0):
        return df2[col] if col in df2.columns else pd.Series([default]*len(df2))
        
    df2["yardline_100"] = safe_get("yardline_100", 50)
    df2["ydstogo"] = safe_get("ydstogo", 10)
    df2["down"] = safe_get("down", 1)
    df2["goal_to_go"] = safe_get("goal_to_go", 0)
    df2["quarter_seconds_remaining"] = safe_get("quarter_seconds_remaining", 900)
    df2["qtr"] = safe_get("qtr", 1)
    df2["score_differential"] = safe_get("score_differential", 0)

    df2["is_redzone"] = (df2["yardline_100"] <= 20).astype(int)
    df2["is_goal_line"] = ((df2["goal_to_go"] == 1) & (df2["yardline_100"] <= 10)).astype(int)
    df2["is_short_yardage"] = ((df2["ydstogo"] <= 2) & (df2["down"] >= 3)).astype(int)
    df2["is_two_minute_drill"] = ((df2["quarter_seconds_remaining"] <= 120) & (df2["qtr"].isin([2, 4]))).astype(int)
    df2["is_close_game_late"] = ((df2["qtr"] == 4) & (df2["score_differential"].abs() <= 8)).astype(int)
    df2["is_midfield_aggression"] = df2["yardline_100"].between(35, 45).astype(int)
    df2["is_deep_redzone"] = (df2["yardline_100"] <= 10).astype(int)
    
    # Run Lane Composite Target Creation
    if "run_location" in df2.columns and "run_gap" in df2.columns:
        def build_lane(row):
            loc = str(row.get("run_location", ""))
            gap = str(row.get("run_gap", ""))
            if loc in ["nan", "None", ""]: return np.nan
            if loc == "middle": return "middle"
            if gap not in ["nan", "None", ""]: return f"{loc}_{gap}"
            return np.nan
        df2["run_lane"] = df2.apply(build_lane, axis=1)

    # Clean categoricals
    for col in CATEGORICAL_FEATURES:
        if col in df2.columns:
            df2[col] = df2[col].fillna("UNKNOWN").astype(str)
        else:
            df2[col] = "UNKNOWN"
            
    return df2


def train_run_models() -> Dict[str, Dict[str, Any]]:
    print("=== Training Run Tendency Models ===")
    start = time.time()
    
    df = load_data()
    df = add_derived_features(df)
    models_info = {}
    
    global_features = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    available_features = [f for f in global_features if f in df.columns]
    
    target = "run_lane"
    if target not in df.columns:
        print(f"Skipping {target}: column missing or could not be derived.")
        return models_info
        
    mask = df[target].notna()
    X_raw = df.loc[mask, available_features].copy()
    y = df.loc[mask, target].copy().astype(str)
    
    # Filter extremely rare gaps
    counts = y.value_counts()
    keep = y.isin(counts[counts >= MIN_SAMPLES_PER_CLASS].index)
    X_raw = X_raw.loc[keep]
    y = y.loc[keep]
    
    if X_raw.empty or y.nunique() < 2:
        print(f"Skipping {target}: insufficient cleaned data")
        return models_info
        
    X_encoded = pd.get_dummies(X_raw, columns=CATEGORICAL_FEATURES, drop_first=True, dtype=int)
    
    X_train, X_test, y_train, y_test = train_test_split(
        X_encoded, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
    
    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=15,
        min_samples_leaf=10,
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )
    
    clf.fit(X_train, y_train)
    acc = accuracy_score(y_test, clf.predict(X_test))
    
    print(f"Accuracy ({target}): {acc:.3f} | Train time: {(time.time() - start):.1f}s")
    
    models_info[target] = {
        "model": clf,
        "classes": clf.classes_.tolist(),
        "feature_columns": X_train.columns.tolist(),
    }
    
    return models_info


def predict_run_metrics(situation_dict: Dict[str, Any], trained_models: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Outputs probability distributions over run lanes for tendency scouting.
    """
    situation_df = pd.DataFrame([situation_dict])
    situation_df = add_derived_features(situation_df)
    
    situation_encoded = pd.get_dummies(
        situation_df, columns=CATEGORICAL_FEATURES, drop_first=True, dtype=int
    )
    
    predictions = {}
    if "run_lane" in trained_models:
        model_info = trained_models["run_lane"]
        model = model_info['model']
        model_features = model_info['feature_columns']
        classes = model_info['classes']
        
        # Align inference columns to the exact schema observed during training
        X_infer = situation_encoded.reindex(columns=model_features, fill_value=0)
        
        # Pull probabilities rather than argmax
        probs = model.predict_proba(X_infer)[0]
        top_indices = np.argsort(probs)[::-1][:3]
        
        lane_predictions = []
        for idx in top_indices:
            lane = classes[idx]
            
            # Split back into legacy gap/location for backward compatibility with routeDrawer
            if lane == "middle":
                loc, gap = "middle", None
            elif "_" in lane:
                loc, gap = lane.split("_", 1)
            else:
                loc, gap = lane, None
                
            lane_predictions.append({
                "run_lane": lane,
                "run_location": loc,
                "run_gap": gap,
                "probability": round(float(probs[idx]), 3)
            })
            
        predictions["run_tendencies"] = lane_predictions
        
    return predictions


if __name__ == "__main__":
    trained_run_models = train_run_models()
    upload_model_to_release(trained_run_models, "run_model.joblib", "run-model")
