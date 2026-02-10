import time
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
import joblib

DATA_FILES = ["Data/merged_pass_model_data_2020.csv"]
DATA_FILES.append("Data/merged_pass_model_data_2021.csv")
DATA_FILES.append("Data/merged_pass_model_data_2022.csv")
DATA_FILES.append("Data/merged_pass_model_data_2023.csv")
DATA_FILES.append("Data/merged_pass_model_data_2024.csv")
OUTPUT_DIR = Path("models")
OUTPUT_DIR.mkdir(exist_ok=True)

TARGETS = [
    "receiver_position",
    "route",
    "offense_personnel",
    "offense_formation",
    "pass_length",
    "pass_location",
]

RANDOM_STATE = 42
TEST_SIZE = 0.2
MIN_SAMPLES_PER_CLASS = 15


def load_first_existing(files: List[str]) -> pd.DataFrame:
    for f in files:
        p = Path(f)
        if p.exists():
            print(f"Loading data from {f}")
            return pd.read_csv(p, low_memory=False)

def add_football_intelligence_features(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    #basic safety for missing columns
    def safe_get(col, default=0):
        return df2[col] if col in df2.columns else pd.Series([default]*len(df2))

    df2["yardline_100"] = safe_get("yardline_100", 50)
    df2["goal_to_go"] = safe_get("goal_to_go", 0)
    df2["down"] = safe_get("down", 1)
    df2["ydstogo"] = safe_get("ydstogo", 10)
    df2["quarter_seconds_remaining"] = safe_get("quarter_seconds_remaining", 900)
    df2["qtr"] = safe_get("qtr", 1)
    df2["score_differential"] = safe_get("score_differential", 0)
    df2["shotgun"] = safe_get("shotgun", 0)
    df2["play_type"] = safe_get("play_type", "pass")

    #Field position
    df2["is_redzone"] = (df2["yardline_100"] <= 20).astype(int)
    df2["is_goal_to_go"] = df2["goal_to_go"].fillna(0).astype(int)
    df2["is_backed_up"] = (df2["yardline_100"] >= 80).astype(int)
    df2["is_midfield_aggression"] = df2["yardline_100"].between(35, 45).astype(int)
    df2["is_deep_redzone"] = (df2["yardline_100"] <= 10).astype(int)

    #Down and distance
    df2["is_third_long"] = ((df2["down"] == 3) & (df2["ydstogo"] >= 7)).astype(int)
    df2["is_third_short"] = ((df2["down"] == 3) & (df2["ydstogo"] <= 3)).astype(int)
    df2["is_second_long"] = ((df2["down"] == 2) & (df2["ydstogo"] >= 8)).astype(int)
    df2["is_first_down"] = (df2["down"] == 1).astype(int)

    #Game situation
    df2["is_two_minute"] = (df2["quarter_seconds_remaining"] <= 120).astype(int)
    df2["is_close_game_late"] = ((df2["qtr"] == 4) & (df2["score_differential"].abs() <= 8)).astype(int)
    df2["is_blowout"] = (df2["score_differential"].abs() >= 21).astype(int)

    #Score context
    df2["is_leading"] = (df2["score_differential"] > 0).astype(int)
    df2["is_trailing"] = (df2["score_differential"] < 0).astype(int)
    df2["score_margin_abs"] = df2["score_differential"].abs()

    #Formation flags
    if "offense_formation" in df2.columns:
        df2["is_empty"] = df2["offense_formation"].str.contains("EMPTY", na=False).astype(int)
        df2["is_heavy"] = df2["offense_formation"].str.contains("JUMBO|HEAVY", na=False).astype(int)
        df2["is_shotgun"] = df2["offense_formation"].str.contains("SHOTGUN", na=False).astype(int)
    else:
        if "shotgun" in df2.columns:
            df2["is_shotgun"] = df2["shotgun"].fillna(0).astype(int)

    #Field segments
    if "yardline_100" in df2.columns:
        df2["field_position"] = pd.cut(
            df2["yardline_100"], bins=[0, 20, 40, 60, 80, 100],
            labels=["redzone", "offensive", "midfield", "defensive", "backed_up"]
        )
    else:
        df2["field_position"] = "midfield"

    return df2

def build_global_feature_set(df: pd.DataFrame) -> List[str]:
    """Construct a compact but informative global feature list."""
    core = [
        "down", "ydstogo", "yardline_100", "goal_to_go", "qtr",
        "quarter_seconds_remaining", "game_seconds_remaining", "score_differential",
        "posteam_timeouts_remaining", "defteam_timeouts_remaining",
        "shotgun", "no_huddle", "posteam", "defteam"
    ]
    derived = [
        "is_redzone", "is_goal_to_go", "is_backed_up",
        "is_third_long", "is_third_short", "is_second_long", "is_first_down",
        "is_two_minute", "is_close_game_late", "is_blowout",
        "is_leading", "is_trailing", "score_margin_abs", "is_shotgun",
        "is_empty", "is_heavy", "field_position", "is_midfield_aggression", "is_deep_redzone"
    ]
    #include a few contextual cols if present
    context = ["temp", "wind", "roof", "surface"]
    possible = core + derived + context
    available = [c for c in possible if c in df.columns]
    print(f"Global feature set contains {len(available)} available columns")
    return available

def global_encode(df: pd.DataFrame, features: List[str]) -> Tuple[pd.DataFrame, List[str]]:
    """Create a single encoded feature matrix used by all targets."""
    X = df[features].copy()
    #fill numeric na with median, categorical with 'NA'
    for col in X.columns:
        if X[col].dtype.kind in "biufc":
            X[col] = X[col].fillna(X[col].median())
        else:
            #Convert categorical columns to plain string dtype first, then fill NAs
            X[col] = X[col].astype("string").fillna("NA")

    #one-hot encode categoricals via pd.get_dummies (drop_first to keep smaller)
    X_encoded = pd.get_dummies(X, drop_first=True)
    feature_cols = X_encoded.columns.tolist()
    print(f"Encoded global feature matrix with {len(feature_cols)} columns")
    return X_encoded, feature_cols

def filter_rare_classes_simple(y: pd.Series, min_samples: int = MIN_SAMPLES_PER_CLASS) -> pd.Series:
    """Combine very rare classes into 'OTHER' or drop if too few samples."""
    counts = y.value_counts()
    rare = counts[counts < min_samples].index
    if len(rare) == 0:
        return y
    y2 = y.copy().astype(str)
    y2[y2.isin(rare)] = "OTHER"
    #if OTHER itself is too small, remove those rows in caller
    return y2

def prepare_for_target(df: pd.DataFrame, X_global: pd.DataFrame, target: str) -> Tuple[pd.DataFrame, pd.Series]:
    if target not in df.columns:
        raise KeyError(target)
    mask = df[target].notna()
    if mask.sum() == 0:
        raise ValueError(f"No rows for target {target}")
    X = X_global.loc[mask].copy()
    y = df.loc[mask, target].copy().astype(str)
    #basic leakage removal (remove target-like columns)
    possible_leaks = ["air_yards", "yards_after_catch", "yards_gained", "epa", "complete_pass"]
    for leak in possible_leaks:
        if leak in X.columns:
            X = X.drop(columns=[leak], errors='ignore')
    #handle rare classes
    y = filter_rare_classes_simple(y)
    #drop rows where target became OTHER but still too rare
    counts = y.value_counts()
    if (counts < MIN_SAMPLES_PER_CLASS).any():
        #drop undersized classes
        keep = y.isin(counts[counts >= MIN_SAMPLES_PER_CLASS].index)
        X = X.loc[keep]
        y = y.loc[keep]
    return X, y

def train_target_model(X: pd.DataFrame, y: pd.Series, target: str) -> Dict[str, Any]:
    print(f"\n ---Training target: {target}")
    print(f"Samples: {len(y)} | Classes: {len(y.unique())}")
    if len(y) < 50 or y.nunique() < 2:
        print(f"Skipping {target}: insufficient data")
        return {}
    #train/test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, random_state=RANDOM_STATE, stratify=y
    )
    #choose RandomForest (robust for categorical-heavy data)
    clf = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )
    start = time.time()
    clf.fit(X_train, y_train)
    elapsed = time.time() - start
    y_pred = clf.predict(X_test)
    acc = accuracy_score(y_test, y_pred)
    print(f"Accuracy ({target}): {acc:.3f} | Train time: {elapsed:.1f}s")
    #limited classification report for small-class targets
    try:
        labels = np.union1d(y_test.unique(), y_pred)
        print(classification_report(y_test, y_pred, labels=labels, zero_division=0))
    except Exception:
        pass
    return {
        "model": clf,
        "accuracy": float(acc),
        "train_time_s": elapsed,
        "classes": clf.classes_.tolist() if hasattr(clf, "classes_") else [],
        "feature_columns": X_train.columns.tolist(),
    }

def train_all_targets(df: pd.DataFrame, targets: List[str]) -> Dict[str, Dict[str, Any]]:
    models_info: Dict[str, Dict[str, Any]] = {}
    features = build_global_feature_set(df)
    if not features:
        print("No features available.")
        return models_info
    X_global, feature_cols = global_encode(df, features)
    #keep the index aligned with df for slicing per-target
    X_global.index = df.index

    for target in targets:
        if target not in df.columns:
            print(f"Skipping {target}: column missing")
            continue
        try:
            X, y = prepare_for_target(df, X_global, target)
            if X.empty or y.nunique() < 2:
                print(f"Skipping {target}: insufficient cleaned data")
                continue
            info = train_target_model(X, y, target)
            if not info:
                continue
            models_info[target] = info
            #save model and metadata
            out_path = OUTPUT_DIR / f"pass_model_{target}.joblib"
            joblib.dump(
                {
                    "model": info["model"],
                    "feature_columns": X.columns.tolist(),
                    "target": target,
                },
                out_path,
            )
            meta = {
                "target": target,
                "accuracy": info["accuracy"],
                "train_time_s": info["train_time_s"],
                "n_features": len(X.columns),
                "n_samples": len(y),
                "classes": info.get("classes", []),
            }
            meta_path = OUTPUT_DIR / f"pass_model_{target}_meta.json"
            with open(meta_path, "w") as fh:
                json.dump(meta, fh, indent=2)
            print(f"Saved model -> {out_path}, metadata -> {meta_path}")
        except Exception as e:
            print(f"Failed for {target}: {e}")
            continue
    return models_info

def print_summary(trained_models: Dict[str, Dict[str, Any]]):
    print("\n" + "="*50)
    print("Training Summary")
    print("="*50)
    if not trained_models:
        print("No models trained.")
        return
    for t, v in trained_models.items():
        print(f"{t:20} | Acc: {v['accuracy']:.3f} | Time: {v['train_time_s']:.1f}s | Classes: {len(v['classes'])}")

def train_pass_models():
    start = time.time()
    print("=== Pass Model ===")
    df = load_first_existing(DATA_FILES)
    #filter to pass plays if play_type exists
    if "play_type" in df.columns:
        df = df[df["play_type"] == "pass"].copy()
    print(f"Initial pass plays: {len(df)}")
    df = add_football_intelligence_features(df)
    trained = train_all_targets(df, TARGETS)
    print_summary(trained)
    print(f"\nTotal time: {(time.time() - start)/60:.2f} minutes")
    return trained

def predict_pass_metrics(situation, trained_models):
    ''' 
        Function that predicts the most optimal pass metrics 
        (including: reciever position, route, offense personnel, offense_formation, pass_length, pass_location)
    '''

    # Convert input to DataFrame with correct column names
    situation_df = pd.DataFrame([situation], columns=['down', 'ydstogo', 'yardline_100', 'goal_to_go', 'quarter_seconds_remaining',
                                                      'half_seconds_remaining', 'game_seconds_remaining', 'score_differential', 
                                                      'posteam_timeouts_remaining', 'defteam_timeouts_remaining', 'posteam', 'defteam',
                                                      'is_midfield_aggression', 'is_deep_redzone'])

    # Add the football intelligence features
    situation_df = add_football_intelligence_features(situation_df)

    # Prepare the feature set
    features = build_global_feature_set(situation_df)
    situation_encoded, feature_cols = global_encode(situation_df, features)
    predictions = {}

    for target, model_info in trained_models.items():
        model = model_info['model']
        model_features = model_info['feature_columns']

        # Ensure the situation_encoded has all the features required by the model
        for col in model_features:
            if col not in situation_encoded.columns:
                situation_encoded[col] = 0
        
        # Reorder columns to match model's expected input
        situation_input = situation_encoded[model_features]

        # Make prediction
        pred = model.predict(situation_input)
        predictions[target] = pred[0]

    return predictions


if __name__ == "__main__":
    # Train the Pass models when running this file separately
    model = train_pass_models()

    # Save the pass model to the models directory
    model_dir = Path("models")
    model_dir.mkdir(exist_ok=True)

    model_path = model_dir / "pass_models.joblib"
    joblib.dump(model, model_path)
    print(f"Pass models saved to {model_path}")
