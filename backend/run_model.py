import pandas as pd
import numpy as np

from typing import Dict, Any, List

from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report

from parse_personnel import add_personnel_features
from add_participation_features import add_participation_features

import joblib
from pathlib import Path


def train_run_models() -> Dict[str, Dict[str, Any]]:
    """
    Trains tendency models ('run_gap', 'run_location', 'offense_formation',
    'offense_personnel') using all available situational, personnel, and
    formation features.
    """

    try:
        pbp_files: List[pd.DataFrame] = [
            pd.read_csv("Data/pbp_2024_0.csv", low_memory=False),
            pd.read_csv("Data/pbp_2024_1.csv", low_memory=False),
        ]
        df: pd.DataFrame = pd.concat(pbp_files, ignore_index=True)
    except FileNotFoundError:
        print("Error: Data files not found in 'Data/' directory. Exiting.")
        return {}

    # Filter for designed runs only
    # This prevents scrambles (intended passes) from biasing the run model
    df_filtered = df[(df["play_type"] == "run") & (df["qb_scramble"] == 0)].copy()

    if df_filtered.empty:
        print("No 'run' plays found. Exiting.")
        return {}

    try:
        part_df: pd.DataFrame = pd.read_csv(
            "Data/pbp_participation_2024.csv",
            low_memory=False,
        )
    except FileNotFoundError:
        print("Warning: participation file not found, skipping personnel/formation features.")
        part_df = None

    if part_df is not None:
        if "old_game_id" in df_filtered.columns and "old_game_id" in part_df.columns:
            game_key_col: str = "old_game_id"
        elif "game_id" in df_filtered.columns and "game_id" in part_df.columns:
            game_key_col = "game_id"
        else:
            game_key_col = None

    if part_df is not None and game_key_col:
        keep_cols: List[str] = [game_key_col, "play_id"]
        extra_part_cols = ["offense_personnel", "defense_personnel", "offense_formation", "defenders_in_box"]
        for col in extra_part_cols:
            if col in part_df.columns:
                keep_cols.append(col)

        part_df = part_df[keep_cols].drop_duplicates(subset=[game_key_col, "play_id"])
        df_filtered = pd.merge(df_filtered, part_df, on=[game_key_col, "play_id"], how="left")
        df_filtered = df_filtered.rename(columns={"offense_personnel": "personnel_off", "defense_personnel": "personnel_def"})
        df_filtered = add_personnel_features(df_filtered)
        df_filtered = add_participation_features(df_filtered)

    # pre-processing
    for col in ["temp", "wind"]:
        if col in df_filtered.columns:
            df_filtered[col] = df_filtered[col].fillna(float(df_filtered[col].median()))

    required_cols = ["yardline_100", "goal_to_go", "ydstogo", "down", "quarter_seconds_remaining", "qtr", "score_differential"]

    if all(col in df_filtered.columns for col in required_cols):
        df_filtered["is_redzone"] = (df_filtered["yardline_100"] <= 20).astype(int)
        df_filtered["is_goal_line"] = ((df_filtered["goal_to_go"] == 1) & (df_filtered["yardline_100"] <= 10)).astype(int)
        df_filtered["is_short_yardage"] = ((df_filtered["ydstogo"] <= 2) & (df_filtered["down"] >= 3)).astype(int)
        df_filtered["is_two_minute_drill"] = ((df_filtered["quarter_seconds_remaining"] <= 120) & (df_filtered["qtr"].isin([2, 4]))).astype(int)
        df_filtered["is_close_game_late"] = ((df_filtered["qtr"] == 4) & (df_filtered["score_differential"].abs() <= 8)).astype(int)
        df_filtered["is_midfield_aggression"] = df_filtered["yardline_100"].between(35, 45).astype(int)
        df_filtered["is_deep_redzone"] = (df_filtered["yardline_100"] <= 10).astype(int)

    base_feature_columns: List[str] = [
        "down", "ydstogo", "yardline_100", "goal_to_go", "qtr",
        "quarter_seconds_remaining", "half_seconds_remaining", "game_seconds_remaining", "score_differential",
        "posteam_timeouts_remaining", "defteam_timeouts_remaining", "posteam", "defteam", 
        "shotgun", "no_huddle", "roof", "surface", "temp", "wind",
        "is_redzone", "is_goal_line", "is_short_yardage", "is_two_minute_drill", "is_close_game_late",
        "is_midfield_aggression", "is_deep_redzone"
    ]

    personnel_numeric = ["off_rb", "off_te", "off_wr", "def_dl", "def_lb", "def_db", "defenders_in_box"]
    personnel_categorical = ["offense_formation", "off_group_bucket", "def_group_bucket"]
    feature_columns = base_feature_columns + personnel_numeric + personnel_categorical

    for num_col in personnel_numeric:
        if num_col in df_filtered.columns:
            df_filtered[num_col] = df_filtered[num_col].fillna(0)

    existing_features = [col for col in feature_columns if col in df_filtered.columns]
    X = df_filtered[existing_features].copy()

    if X.empty:
        return {}

    categorical_cols = ["posteam", "defteam", "roof", "surface", "qtr", "offense_formation", "off_group_bucket", "def_group_bucket"]
    existing_categorical = [col for col in categorical_cols if col in X.columns]
    X_processed = pd.get_dummies(X, columns=existing_categorical, drop_first=True).fillna(0)
    trained_models: Dict[str, Dict[str, Any]] = {}
    target_columns = ["run_gap", "run_location", "offense_formation", "personnel_off"]

    for target in target_columns:
        if target not in df_filtered.columns:
            continue

        y_tend = df_filtered[target]
        valid_indices = y_tend.dropna().index
        y_clean = y_tend.loc[valid_indices]
        X_to_use = X_processed.loc[valid_indices].copy()
        

        class_counts = y_clean.value_counts()
        valid_mask = y_clean.isin(class_counts[class_counts > 1].index)
        X_clean = X_to_use.loc[valid_mask]
        y_clean = y_clean.loc[valid_mask]

        if X_clean.empty or y_clean.nunique() < 2:
            continue
        
        X_train, X_test, y_train, y_test = train_test_split(X_clean, y_clean, test_size=0.2, random_state=42, stratify=y_clean)
        
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        model = LogisticRegression(
            random_state=42,
            max_iter=2000, 
            class_weight='balanced' 
        )
        
        model.fit(X_train_scaled, y_train)

        trained_models[target] = {
            "model": model,
            "columns": X_train.columns.tolist(),
            "scaler": scaler 
        }

    return trained_models


def predict_run_metrics(situation, trained_models):
    ''' 
        Function that predicts the most optimal run gap and location 
        with success probability for this specific run play 
        based on the trained run models. 
    '''
    situation_df = pd.DataFrame([situation], columns=['down', 'ydstogo', 'yardline_100', 'goal_to_go', 'quarter_seconds_remaining',
                                                      'half_seconds_remaining', 'game_seconds_remaining', 'score_differential', 
                                                      'posteam_timeouts_remaining', 'defteam_timeouts_remaining', 'posteam', 'defteam', 
                                                      'is_midfield_aggression', 'is_deep_redzone'])
    
    situation_df["is_redzone"] = (situation_df["yardline_100"] <= 20).astype(int)
    situation_df["is_goal_line"] = (
        (situation_df["goal_to_go"] == 1) & (situation_df["yardline_100"] <= 10)
    ).astype(int)
    situation_df["is_short_yardage"] = (
        (situation_df["ydstogo"] <= 2) & (situation_df["down"] >= 3)
    ).astype(int)
    
    # Infer quarter from time remaining (simple heuristic)
    if situation[6] > 2700:  # game_seconds_remaining
        qtr = 1
    elif situation[6] > 1800:
        qtr = 2
    elif situation[6] > 900:
        qtr = 3
    else:
        qtr = 4
    
    situation_df["qtr"] = qtr
    situation_df["is_two_minute_drill"] = (
        (situation_df["quarter_seconds_remaining"] <= 120)
        & (situation_df["qtr"].isin([2, 4]))
    ).astype(int)
    situation_df["is_close_game_late"] = (
        (situation_df["qtr"] == 4)
        & (situation_df["score_differential"].abs() <= 8)
    ).astype(int)

    situation_df["shotgun"] = 0  # default value
    situation_df["no_huddle"] = 0  # default value
    situation_df["roof"] = "outdoors"  # default value
    situation_df["surface"] = "grass"  # default value
    situation_df["temp"] = 70  # default value
    situation_df["wind"] = 0  # default value

    categorical_cols = ["posteam", "defteam", "roof", "surface", "qtr"]
    situation_encoded = pd.get_dummies(
        situation_df,
        columns=categorical_cols,
        drop_first=True,
    )
    
    # Get the situation model to predict success probability first
    sit_model_info = trained_models.get("situation")
    if sit_model_info:
        sit_model = sit_model_info["model"]
        sit_columns = sit_model_info["columns"]

        for col in sit_columns:
            if col not in situation_encoded.columns:
                situation_encoded[col] = 0
        
        situation_encoded = situation_encoded[sit_columns]
        
        # Predict success probability
        success_prob = sit_model.predict_proba(situation_encoded)[0, 1]
        print(f"Predicted run success probability: {success_prob:.3f}")
        situation_encoded["predicted_run_success_prob"] = success_prob
    
    # Predict the most optimal metric (gap, location) for the run play 
    run_metrics = {}
    for metric in ["run_gap", "run_location", "offense_formation", "personnel_off"]:
        if metric in trained_models:
            model_info = trained_models[metric]
            model = model_info["model"]
            model_columns = model_info["columns"]

            for col in model_columns:
                if col not in situation_encoded.columns:
                    situation_encoded[col] = 0

            situation_for_prediction = situation_encoded[model_columns]
            
            # Predict
            prediction = model.predict(situation_for_prediction)[0]
            run_metrics[metric] = prediction
            print(f"Predicted {metric}: {prediction}")

    return run_metrics



if __name__ == "__main__":
    # Train the Run models when running this file separately
    print("Starting all run model training")
    all_models: Dict[str, Dict[str, Any]] = train_run_models()

    # Save the trained run models to the models directory
    model_dir = Path("models")
    model_dir.mkdir(exist_ok=True)
    model_path = model_dir / "run_models.joblib"
    joblib.dump(all_models, model_path)
    print(f"Run models saved to {model_path}")

    if all_models:
        print("\nAll model training complete")
        print(f"Trained {len(all_models)} models: {list(all_models.keys())}")
    else:
        print("\nModel training failed ---")
