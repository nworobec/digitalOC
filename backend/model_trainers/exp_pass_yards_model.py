import pandas as pd

try:
    from .inference import encode_inference, align_inference
except ImportError:
    from inference import encode_inference, align_inference
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LinearRegression, Ridge, LogisticRegression
from sklearn.ensemble import RandomForestRegressor, GradientBoostingClassifier
from sklearn.metrics import mean_squared_error, r2_score, accuracy_score, classification_report
import joblib
import json
from pathlib import Path
import io
import sys
import os

try:
    from .TeamElo import PlayClassifier, get_team_elos
except ImportError:
    sys.path.insert(0, os.path.dirname(__file__))
    from TeamElo import PlayClassifier, get_team_elos


BASE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = BASE_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
MODEL_DIR = BACKEND_DIR / "models"


def train_exp_yards_model_pass():
    '''
    Two-stage expected yards model for passing plays:
      Stage 1: Completion probability classifier (is the pass caught?)
      Stage 2: Yards-if-complete regression (how many yards if caught?)
      Expected Yards = P(complete) * E[yards | complete]
    '''

    # Open both 2024 Play-by-Play CSV files and combine them
    pbp_files = [
        pd.read_csv(DATA_DIR / "pbp_2024_0.csv"),
        pd.read_csv(DATA_DIR / "pbp_2024_1.csv")
    ]
    df = pd.concat(pbp_files, ignore_index=True)

    # Filter columns that only contain "pass" for play_type
    df_filtered = df[df['play_type'].isin(['pass'])].copy()
    df_filtered["play_category"] = df_filtered.apply(PlayClassifier.get_category, axis=1)

    # Create a column in the input variables for the Offense Team's ELO Rating
    def get_elo(row):
        team = row["posteam"]
        category = row["play_category"]
        team_elos = get_team_elos()
        return team_elos.get(team, {}).get(category, 1000.0)
    df_filtered["elo_score"] = df_filtered.apply(get_elo, axis=1)

    # Intergrate the pbp_participation_file to get offense formation and personnel for each play
    pbp_participation_file = pd.read_csv(DATA_DIR / "pbp_participation_2024.csv")
    def get_participation_info(row):
        game_id = row["game_id"]
        play_id = row["play_id"]
        participation_row = pbp_participation_file[(pbp_participation_file["nflverse_game_id"] == game_id) & (pbp_participation_file["play_id"] == play_id)]
        
        if not participation_row.empty:
            return participation_row.iloc[0]["offense_formation"], participation_row.iloc[0]["offense_personnel"], participation_row.iloc[0].get("defense_coverage_type", "UNKNOWN")
        else:
            return np.nan, np.nan, "UNKNOWN"
    df_filtered["offense_formation"], df_filtered["offense_personnel"], df_filtered["defense_coverage_type"] = zip(*df_filtered.apply(get_participation_info, axis=1))

    # Situational features
    df_filtered["is_redzone"] = (df_filtered["yardline_100"] <= 20).astype(int)
    df_filtered["is_goal_line"] = ((df_filtered["goal_to_go"] == 1) & (df_filtered["yardline_100"] <= 10)).astype(int)
    df_filtered["is_short_yardage"] = ((df_filtered["ydstogo"] <= 2) & (df_filtered["down"] >= 3)).astype(int)

    # Exclude sacks and interceptions — only model true pass attempts (complete or incomplete)
    df_passes = df_filtered[(df_filtered['sack'] == 0) & (df_filtered['interception'] == 0)].copy()
    print(f"Pass plays after excluding sacks/INTs: {df_passes.shape[0]}")

    # Feature columns (shared between both stages)
    feature_cols = ['pass_length', 'pass_location', 'air_yards', 'posteam', 'defteam', 'elo_score', 'down', 'ydstogo', 
                    'yardline_100', 'goal_to_go', 'quarter_seconds_remaining', 'half_seconds_remaining', 
                    'game_seconds_remaining', 'score_differential', 'posteam_timeouts_remaining', 
                    'defteam_timeouts_remaining', 'offense_formation', 'offense_personnel',
                    'is_redzone', 'is_goal_line', 'is_short_yardage', 'defense_coverage_type']
    categorical_cols = ['posteam', 'defteam', 'pass_length', 'pass_location', 'offense_formation', 'offense_personnel', 'defense_coverage_type']

    # ========== STAGE 1: Completion Probability Model ==========
    print("\n" + "="*60)
    print("STAGE 1: Training Completion Probability Model")
    print("="*60)

    X_all = df_passes[feature_cols]
    y_completion = df_passes['complete_pass'].astype(int)  # 1 = complete, 0 = incomplete
    print(f"Completion rate: {y_completion.mean():.3f}")

    X_train_cp, X_test_cp, y_train_cp, y_test_cp = train_test_split(
        X_all, y_completion, test_size=0.2, random_state=42
    )

    # One-hot encode
    X_train_cp_enc = pd.get_dummies(X_train_cp, columns=categorical_cols, drop_first=True)
    X_test_cp_enc = pd.get_dummies(X_test_cp, columns=categorical_cols, drop_first=True)
    X_train_cp_enc, X_test_cp_enc = X_train_cp_enc.align(X_test_cp_enc, join='left', axis=1, fill_value=0)

    # Clean missing values
    train_idx = X_train_cp_enc.dropna().index.intersection(y_train_cp.dropna().index)
    X_train_cp_clean = X_train_cp_enc.loc[train_idx]
    y_train_cp_clean = y_train_cp.loc[train_idx]
    test_idx = X_test_cp_enc.dropna().index.intersection(y_test_cp.dropna().index)
    X_test_cp_clean = X_test_cp_enc.loc[test_idx]
    y_test_cp_clean = y_test_cp.loc[test_idx]
    print(f"Completion model train size: {X_train_cp_clean.shape[0]}, test size: {X_test_cp_clean.shape[0]}")

    # Train completion probability classifier
    completion_model = GradientBoostingClassifier(n_estimators=200, max_depth=4, learning_rate=0.1, random_state=42)
    completion_model.fit(X_train_cp_clean, y_train_cp_clean)

    # Evaluate completion model
    y_pred_cp = completion_model.predict(X_test_cp_clean)
    y_pred_cp_proba = completion_model.predict_proba(X_test_cp_clean)[:, 1]
    print(f"Completion Model Accuracy: {accuracy_score(y_test_cp_clean, y_pred_cp):.4f}")
    print(classification_report(y_test_cp_clean, y_pred_cp, target_names=['Incomplete', 'Complete']))

    # ========== STAGE 2: Yards-If-Complete Regression ==========
    print("\n" + "="*60)
    print("STAGE 2: Training Yards-If-Complete Regression Model")
    print("="*60)

    # Train only on completed passes
    df_complete = df_passes[df_passes['complete_pass'] == 1].copy()
    print(f"Completed passes for yards model: {df_complete.shape[0]}")

    X_yards = df_complete[feature_cols]
    y_yards = df_complete['epa'].clip(-5, 40)  # Wider clip range since these are all completions

    X_train_yd, X_test_yd, y_train_yd, y_test_yd = train_test_split(
        X_yards, y_yards, test_size=0.2, random_state=42
    )

    # One-hot encode
    X_train_yd_enc = pd.get_dummies(X_train_yd, columns=categorical_cols, drop_first=True)
    X_test_yd_enc = pd.get_dummies(X_test_yd, columns=categorical_cols, drop_first=True)
    X_train_yd_enc, X_test_yd_enc = X_train_yd_enc.align(X_test_yd_enc, join='left', axis=1, fill_value=0)

    # Clean missing values
    train_idx_yd = X_train_yd_enc.dropna().index.intersection(y_train_yd.dropna().index)
    X_train_yd_clean = X_train_yd_enc.loc[train_idx_yd]
    y_train_yd_clean = y_train_yd.loc[train_idx_yd]
    test_idx_yd = X_test_yd_enc.dropna().index.intersection(y_test_yd.dropna().index)
    X_test_yd_clean = X_test_yd_enc.loc[test_idx_yd]
    y_test_yd_clean = y_test_yd.loc[test_idx_yd]
    print(f"Yards model train size: {X_train_yd_clean.shape[0]}, test size: {X_test_yd_clean.shape[0]}")

    # Train yards-if-complete regression
    yards_model = Ridge(alpha=1.0)
    yards_model.fit(X_train_yd_clean, y_train_yd_clean)

    # Evaluate yards-if-complete model (on completions only)
    y_pred_yd = yards_model.predict(X_test_yd_clean)
    mse_yards = mean_squared_error(y_test_yd_clean, y_pred_yd)
    r2_yards = r2_score(y_test_yd_clean, y_pred_yd)
    print(f"Yards-If-Complete MSE: {mse_yards:.3f}")
    print(f"Yards-If-Complete R²: {r2_yards:.4f}")

    # ========== COMBINED: Expected Yards Evaluation ==========
    print("\n" + "="*60)
    print("COMBINED: Expected Yards = P(complete) * E[yards|complete]")
    print("="*60)

    # Evaluate on the full test set (complete + incomplete passes)
    X_test_full_enc = pd.get_dummies(X_test_cp, columns=categorical_cols, drop_first=True)
    X_test_full_cp = X_test_full_enc.reindex(columns=X_train_cp_clean.columns, fill_value=0)
    X_test_full_yd = X_test_full_enc.reindex(columns=X_train_yd_clean.columns, fill_value=0)

    # Drop rows that had NaN in original features
    valid_idx = X_test_full_cp.dropna().index.intersection(y_test_cp.dropna().index)
    X_test_full_cp_clean = X_test_full_cp.loc[valid_idx]
    X_test_full_yd_clean = X_test_full_yd.loc[valid_idx]

    # Get the actual yards_gained for the full test set
    y_test_actual = df_passes.loc[valid_idx, 'yards_gained'].clip(-5, 40)

    # Combined prediction: P(complete) * E[yards | complete]
    p_complete = completion_model.predict_proba(X_test_full_cp_clean)[:, 1]
    yards_if_complete = yards_model.predict(X_test_full_yd_clean)
    y_pred_combined = p_complete * yards_if_complete

    mse_combined = mean_squared_error(y_test_actual, y_pred_combined)
    r2_combined = r2_score(y_test_actual, y_pred_combined)
    print(f"Combined Expected Yards MSE: {mse_combined:.3f}")
    print(f"Combined Expected Yards R²:  {r2_combined:.4f}")

    # Compare with old single-stage approach
    print("\nPredicted vs Actual values for the first 10 test samples:")
    for i in range(min(10, len(y_pred_combined))):
        print(f"P(complete): {p_complete[i]:.2f}, Yards if complete: {yards_if_complete[i]:.1f}, "
              f"Expected: {y_pred_combined[i]:.2f}, Actual: {y_test_actual.iloc[i]}")

    return completion_model, yards_model


def predict_exp_yards_pass(input_dict, completion_model, yards_model):
    ''' Predict expected yards for a passing play using the two-stage model '''

    # Prepare input data
    input_df = pd.DataFrame([input_dict])

    # One-hot encode categorical columns
    categorical_cols = ['posteam', 'defteam', 'pass_length', 'pass_location', 'offense_formation', 'offense_personnel', 'defense_coverage_type']
    input_df_encoded = encode_inference(input_df, categorical_cols)

    # Align with completion model columns and predict P(complete)
    cp_cols = completion_model.feature_names_in_
    input_cp = align_inference(input_df_encoded, cp_cols, "pass.completion")
    p_complete = completion_model.predict_proba(input_cp)[:, 1][0]

    # Align with yards model columns and predict E[yards | complete]
    yd_cols = yards_model.feature_names_in_
    input_yd = align_inference(input_df_encoded, yd_cols, "pass.outcome")
    yards_if_complete = yards_model.predict(input_yd)[0]

    expected_yards = p_complete * yards_if_complete
    return expected_yards, p_complete, yards_if_complete



if __name__ == "__main__":
    try:
        from .upload_to_release import upload_model_to_release
    except ImportError:
        from upload_to_release import upload_model_to_release

    # Save the completion probability and yards-if-complete models to GitHub Releases
    completion_model, yards_model = train_exp_yards_model_pass()
    upload_model_to_release(completion_model, "completion_prob_model.joblib", "completion-prob-model")
    upload_model_to_release(yards_model, "exp_pass_yards_model.joblib", "exp-pass-yards-model")