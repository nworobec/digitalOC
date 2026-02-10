# Import necessary libraries
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report
import joblib
import json
from pathlib import Path
from TeamElo import PlayClassifier, team_elos


def train_pbp_model():
    pbp_files = [pd.read_csv("Data/pbp_2024_0.csv", low_memory=False), pd.read_csv("Data/pbp_2024_1.csv", low_memory=False)]
    df = pd.concat(pbp_files, ignore_index=True).copy()

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
        return team_elos.get(team, {}).get(category, 1000.0)

    df_filtered["elo_score"] = df_filtered.apply(get_elo, axis=1)

    X_features = [
        'down', 'ydstogo', 'yardline_100', 'goal_to_go', 
        'quarter_seconds_remaining', 'half_seconds_remaining', 
        'game_seconds_remaining', 'score_differential', 
        'posteam_timeouts_remaining', 'defteam_timeouts_remaining', 
        'posteam', 'defteam', 'elo_score'
    ]
    
    X = df_filtered[X_features]
    # Target is now Intent (1 for Pass, 0 for Run)
    y = df_filtered['is_pass_intent'] 

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    categorical_cols = ['posteam', 'defteam']
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

def predict_play(situation, trained_model, feature_columns):
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

    situation_df = pd.DataFrame([situation], columns=['down', 'ydstogo', 'yardline_100', 'goal_to_go', 'quarter_seconds_remaining',
                                                      'half_seconds_remaining', 'game_seconds_remaining', 'score_differential', 
                                                      'posteam_timeouts_remaining', 'defteam_timeouts_remaining', 'posteam', 'defteam', 'is_midfield_aggression', 'is_deep_redzone'])

    categorical_cols = ['posteam', 'defteam']
    situation_encoded = pd.get_dummies(situation_df, columns=categorical_cols, drop_first=True)

    for col in feature_columns:
        if col not in situation_encoded.columns:
            situation_encoded[col] = 0

    situation_encoded = situation_encoded[feature_columns]
    prediction = trained_model.predict(situation_encoded)
    prediction_proba = trained_model.predict_proba(situation_encoded)

    print("======================================")
    print(f"Predicted Play Type: {prediction}")
    print(f"Confidence {prediction_proba}")
    print("======================================")
    print()

    return prediction[0], prediction_proba[0]   

  
if __name__ == "__main__": 
    # Train the PBP situation model when running this file separately
    model, feature_columns = train_pbp_model()

    # Save the model and feature columns to the models directory
    model_dir = Path("models")
    model_dir.mkdir(exist_ok=True)
    
    # Save the trained model using joblib
    model_path = model_dir / "pbp_situation_model.joblib"
    joblib.dump(model, model_path)
    print(f"Model saved to {model_path}")
    
    # Save feature columns as JSON metadata
    #feature_columns = X_train_clean.columns.tolist()
    metadata = {
        "feature_columns": feature_columns,
        "model_type": "RandomForestClassifier"
    }
    meta_path = model_dir / "pbp_situation_model_meta.json"
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"Metadata saved to {meta_path}")
