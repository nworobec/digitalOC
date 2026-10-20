# Import necessary libraries
import pandas as pd

try:
    from .inference import encode_inference, align_inference
except ImportError:
    from inference import encode_inference, align_inference
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
import joblib
import json
from pathlib import Path
import sys
import os
import io

try:
    from .add_additional_pbp_features import add_additional_pbp_features
    from .TeamElo import PlayClassifier, get_team_elos
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from add_additional_pbp_features import add_additional_pbp_features
    from TeamElo import PlayClassifier, get_team_elos



def train_pbp_model():
    pbp_files = [pd.read_csv("../data/pbp_2024_0.csv", low_memory=False), pd.read_csv("../data/pbp_2024_1.csv", low_memory=False)]
    df = pd.concat(pbp_files, ignore_index=True).copy()
    df = add_additional_pbp_features(df)

    part_df = pd.read_csv("../data/pbp_participation_2024.csv", low_memory=False)
    # accounting for nflverse column naming differences
    part_df = part_df.rename(columns={"nflverse_game_id": "game_id"})
    df = pd.merge(df, part_df[["game_id", "play_id", "defense_coverage_type"]], on=["game_id", "play_id"], how="left")
    df['defense_coverage_type'] = df['defense_coverage_type'].fillna('UNKNOWN')

    df_filtered = df[df['play_type'].isin(['run', 'pass'])].copy()

    # Filtering garbage time
    df_filtered = df_filtered[df_filtered['score_differential'].abs() <= 16]

    # Defining pass intent:
    # We use qb_dropback to identify plays where the intent was to pass
    # This correctly categorizes sacks and scrambles as "Pass Intent"
    df_filtered['is_pass_intent'] = df_filtered['qb_dropback'].fillna(0).astype(int)

    df_filtered["play_category"] = df_filtered.apply(PlayClassifier.get_category, axis=1)

    def get_elo(row):
        team = row["posteam"]
        category = row["play_category"]
        team_elos = get_team_elos()
        return team_elos.get(team, {}).get(category, 1000.0)

    df_filtered["elo_score"] = df_filtered.apply(get_elo, axis=1)

    X_features = [
        'down', 'ydstogo', 'yardline_100', 'goal_to_go',
        'quarter_seconds_remaining', 'half_seconds_remaining',
        'game_seconds_remaining', 'score_differential',
        'posteam_timeouts_remaining', 'defteam_timeouts_remaining',
        'posteam', 'defteam', 'elo_score',
        # --- NEW SEQUENCE FEATURES ---
        'prev_is_pass', 'prev_is_run', 'prev_yards_gained',
        'two_consecutive_runs', 'two_consecutive_passes', 'defense_coverage_type'
    ]

    X = df_filtered[X_features]
    # Target is now Intent (1 for Pass, 0 for Run)
    y = df_filtered['is_pass_intent']

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    categorical_cols = ['posteam', 'defteam', 'defense_coverage_type']
    X_train_encoded = pd.get_dummies(X_train, columns=categorical_cols, drop_first=True)
    X_test_encoded = pd.get_dummies(X_test, columns=categorical_cols, drop_first=True)
    X_train_encoded, X_test_encoded = X_train_encoded.align(X_test_encoded, join='left', axis=1, fill_value=0)

    # Clean missing values
    train_complete_idx = X_train_encoded.dropna().index.intersection(y_train.dropna().index)
    X_train_clean = X_train_encoded.loc[train_complete_idx]
    y_train_clean = y_train.loc[train_complete_idx]

    test_complete_idx = X_test_encoded.dropna().index.intersection(y_test.dropna().index)
    X_test_clean = X_test_encoded.loc[test_complete_idx]
    y_test_clean = y_test.loc[test_complete_idx]

    # Weight balancing
    # 1 = Pass Intent, 0 = Run Intent
    custom_weights = {0: 1.0, 1: 1.5}

    model = RandomForestClassifier(
        n_estimators=100,
        class_weight=custom_weights,
        random_state=42
    )

    model.fit(X_train_clean, y_train_clean)

    return model, X_train_clean.columns.tolist()


def predict_play(situation, trained_model):
    ''' Use the situation to determine the most optimal play type '''
    print(f"Down: {situation[0]}")
    print(f"Yards to go: {situation[1]}")
    print(f"Distance to end zone: {situation[2]}")
    print(f"Goal to go: {situation[3]}")
    print(f"Quarter seconds remaining: {situation[4]}")
    print(f"Half seconds remaining: {situation[5]}")
    print(f"Game seconds remaining: {situation[6]}")
    print(f"Score differential: {situation[7]}")
    print(f"Offensive team timeouts remaining: {situation[8]}")
    print(f"Defensive team timeouts remaining: {situation[9]}")
    print(f"Offensive team: {situation[10]}")
    print(f"Defensive team: {situation[11]}")
    print()

    # Load the play-by-play situation feature columns
    _features_path = Path(__file__).parent / "pbp_situation_features.json"
    with open(_features_path, 'r') as f:
        metadata = json.load(f)
    feature_columns = getattr(trained_model, "feature_names_in_", metadata["feature_columns"])

    situation_df = pd.DataFrame([situation], columns=['down', 'ydstogo', 'yardline_100', 'goal_to_go', 'quarter_seconds_remaining',
         'half_seconds_remaining', 'game_seconds_remaining', 'score_differential',
         'posteam_timeouts_remaining', 'defteam_timeouts_remaining', 'posteam', 'defteam',
         'is_midfield_aggression', 'is_deep_redzone',
         'prev_is_pass', 'prev_is_run', 'prev_yards_gained',
         'two_consecutive_runs', 'two_consecutive_passes', 'defense_coverage_type'])

    categorical_cols = ['posteam', 'defteam', 'defense_coverage_type']
    situation_encoded = encode_inference(situation_df, categorical_cols)

    for col in feature_columns:
        if col not in situation_encoded.columns:
            situation_encoded[col] = 0

    situation_encoded = align_inference(situation_encoded, feature_columns, "situation")
    prediction = trained_model.predict(situation_encoded)
    prediction_proba = trained_model.predict_proba(situation_encoded)

    print("======================================")
    print(f"Predicted Play Type: {prediction}")
    print(f"Confidence {prediction_proba}")
    print("======================================")
    print()

    return prediction[0], prediction_proba[0]


if __name__ == "__main__":
    try:
        from .upload_to_release import upload_model_to_release
    except ImportError:
        from upload_to_release import upload_model_to_release

    # Train the PBP situation model when running this file separately
    model, feature_columns = train_pbp_model()

    # Save the PBP situation model to GitHub Releases
    upload_model_to_release(model, "pbp_situation_model.joblib", "pbp-model")

    # Save the Feature Columns locally
    metadata = {
        "feature_columns": feature_columns,
        "model_type": "RandomForestClassifier"
    }
    meta_path = Path(__file__).parent / "pbp_situation_features.json"
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"PBP Feature Columns successfully saved to {meta_path}")
