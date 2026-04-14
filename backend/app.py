import base64
import io
from flask import Flask, jsonify, request
from flask_cors import CORS
import joblib
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for Flask
import matplotlib.pyplot as plt
import urllib.request

from model_trainers.pbp_situation_model import predict_play
from model_trainers.run_model import predict_run_metrics
from model_trainers.pass_model import predict_pass_metrics
from model_trainers.exp_run_yards_model import predict_exp_yards_run
from model_trainers.exp_pass_yards_model import predict_exp_yards_pass
from routeDrawer.playDraw import visualize_play


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Enable CORS for all routes and origins


# Load the PBP, run, pass, and expected yards models from GitHub Releases when the application starts
def load_model_from_url(url: str):
    with urllib.request.urlopen(url) as response:
        buffer = io.BytesIO(response.read())
    return joblib.load(buffer)

BASE_URL = "https://github.com/nworobec/digitalOC/releases/download"

pbp_model = load_model_from_url(f"{BASE_URL}/pbp-model/pbp_situation_model.joblib")
run_models = load_model_from_url(f"{BASE_URL}/run-model/run_model.joblib")
pass_models = load_model_from_url(f"{BASE_URL}/pass-model/pass_model.joblib")
exp_run_yards_model = load_model_from_url(f"{BASE_URL}/exp-run-yards-model/exp_run_yards_model.joblib")
completion_prob_model = load_model_from_url(f"{BASE_URL}/completion-prob-model/completion_prob_model.joblib")
exp_pass_yards_model = load_model_from_url(f"{BASE_URL}/exp-pass-yards-model/exp_pass_yards_model.joblib")


@app.route("/", methods=['GET'])
def home():
    return "<h1>Server is working</h1>"


@app.route("/suggestPlay", methods=['POST'])
def suggest_play():
    ''' Endpoint from the React frontend to get play suggestion based on the incoming situation and history '''
    
    # Extract the JSON payload sent by React
    data = request.get_json()
    current_situation = data.get('current_situation', {})
    print(f"Received situation: {current_situation}")
    play_history = data.get('play_history', []) # Array of previous plays in this drive
    
    # Extract base features
    yardline = current_situation.get('yardline_100', 50)
    score_diff = current_situation.get('score_differential', 0)
    
    if abs(score_diff) > 16:
        print("NOTICE: Game state is non-competitive. Suggestion may be biased by clock-management.")

    is_midfield_aggression = 1 if 35 <= yardline <= 45 else 0
    is_deep_redzone = 1 if yardline <= 10 else 0

    # Calculate sequence features dynamically from the play_history array
    prev_is_pass = 0
    prev_is_run = 0
    prev_yards_gained = 0
    two_consecutive_runs = 0
    two_consecutive_passes = 0
    
    if len(play_history) > 0:
        last_play = play_history[-1]
        prev_is_pass = 1 if last_play.get('play_type') == 'pass' else 0
        prev_is_run = 1 if last_play.get('play_type') == 'run' else 0
        prev_yards_gained = last_play.get('yards_gained', 0)
        
    if len(play_history) >= 2:
        two_plays_ago = play_history[-2]
        if last_play.get('play_type') == 'run' and two_plays_ago.get('play_type') == 'run':
            two_consecutive_runs = 1
        if last_play.get('play_type') == 'pass' and two_plays_ago.get('play_type') == 'pass':
            two_consecutive_passes = 1

    # Build the final situation array in the exact order the prediction functions expect
    situation = [
        current_situation.get('down', 1),
        current_situation.get('ydstogo', 10),
        yardline,
        current_situation.get('goal_to_go', 0),
        current_situation.get('quarter_seconds_remaining', 900),
        current_situation.get('half_seconds_remaining', 1800),
        current_situation.get('game_seconds_remaining', 3600),
        score_diff,
        current_situation.get('posteam_timeouts_remaining', 3),
        current_situation.get('defteam_timeouts_remaining', 3),
        current_situation.get('posteam', 'UNK'),
        current_situation.get('defteam', 'UNK'),
        is_midfield_aggression,
        is_deep_redzone,
        # --- NEW SEQUENCE FEATURES ---
        prev_is_pass,
        prev_is_run,
        prev_yards_gained,
        two_consecutive_runs,
        two_consecutive_passes,
        current_situation.get('defense_coverage_type', 'UNKNOWN')
    ]

    # Predict whether the play type should be a run or pass
    prediction_int, confidence = predict_play(situation, trained_model=pbp_model)

    # 1 = Pass Intent (Passes, Sacks, Scrambles), 0 = Run Intent
    prediction = 'pass' if prediction_int == 1 else 'run'
    
    exp_yards = None
    play_visualization = None

    # Depending on the prediction, feed it into the run or pass model
    if prediction == 'run':
        run_prediction = predict_run_metrics(situation, trained_models=run_models)
        run_gap = run_prediction['run_gap']
        run_location = run_prediction['run_location']
        offense_formation = run_prediction['offense_formation']
        personnel_off = run_prediction['personnel_off']

        # Modify the offense personnel to get only the RBs, WRs, and TEs when visualizing the play
        personnel_rb_wr_te = ', '.join([part for part in personnel_off.split(', ') if any(pos in part for pos in ['RB', 'WR', 'TE'])])

        run_play_input = {
            "yardline_100": yardline,
            "down": situation[0],
            "ydstogo": situation[1],
            "pass_length": None,
            "pass_location": None, 
            "air_yards": None, 
            "run_location": run_location,
            "run_gap": run_gap,
            "rusher": 'N/A', 
            "receiver": None, 
            "offense_formation": offense_formation,
            "offense_personnel": personnel_rb_wr_te,
            "route": None,
            "involved_player_position": "RB",
            "posteam": situation[10],
            "defteam": situation[11],
            "defense_coverage_type": situation[19]
        }

        exp_yards = str(predict_exp_yards_run(run_play_input, exp_run_yards_model).round(2))
        play_visualization = visualize_play(run_play_input)

    elif prediction == 'pass':
        pass_prediction = predict_pass_metrics(situation, trained_models=pass_models)
        pass_length = pass_prediction['pass_length']
        pass_location = pass_prediction['pass_location']
        offense_formation = pass_prediction['offense_formation']
        offense_personnel = pass_prediction['offense_personnel']
        route = pass_prediction['route']
        receiver_position = pass_prediction['receiver_position']

        pass_play_input = {
            "yardline_100": yardline,
            "down": situation[0],
            "ydstogo": situation[1],
            "pass_length": pass_length,
            "pass_location": pass_location,
            "air_yards": 10, # Placeholder value    
            "run_location": None,
            "run_gap": None,
            "rusher": None,
            "receiver": 'N/A',
            "offense_formation": offense_formation,
            "offense_personnel": offense_personnel,
            "route": route,
            "involved_player_position": receiver_position,
            "posteam": situation[10],
            "defteam": situation[11],
            "defense_coverage_type": situation[19]
        }

        p_complete_and_exp_yards = predict_exp_yards_pass(pass_play_input, completion_prob_model, exp_pass_yards_model)
        exp_yards = (
            f"{p_complete_and_exp_yards[0].round(2)}\n"
            f"Completion Probability: {(p_complete_and_exp_yards[1] * 100).round(0)}%"
        )
        play_visualization = visualize_play(pass_play_input)

    play_visualization_b64 = base64.b64encode(play_visualization.getvalue()).decode('utf-8')
    return jsonify({"expected_yards": exp_yards, "play_visualization": play_visualization_b64})


if __name__ == "__main__":
    app.run(debug=True, port=5000, host='0.0.0.0', use_reloader=False)