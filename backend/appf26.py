import base64
import io
import json
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS
import joblib
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for Flask
import matplotlib.pyplot as plt

from model_trainers.pbpSituationNEW import predict_play
from model_trainers.runModelNEW import predict_run_metrics
from model_trainers.passModelNEW import predict_pass_metrics
from routeDrawer.playDraw import visualize_play

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Load the core tendency models from GitHub Releases
def load_model_from_url(url: str):
    with urllib.request.urlopen(url) as response:
        buffer = io.BytesIO(response.read())
    return joblib.load(buffer)

BASE_URL = "https://github.com/nworobec/digitalOC/releases/download"

# Load Models
pbp_model = load_model_from_url(f"{BASE_URL}/pbp-model/pbp_situation_model.joblib")
run_models = load_model_from_url(f"{BASE_URL}/run-model/run_model.joblib")
pass_models = load_model_from_url(f"{BASE_URL}/pass-model/pass_model.joblib")

# Load PBP Feature Columns from local JSON generated during training
PBP_META_PATH = Path(__file__).parent / "model_trainers" / "pbp_situation_features.json"
try:
    with open(PBP_META_PATH, 'r') as f:
        pbp_feature_columns = json.load(f)["feature_columns"]
except FileNotFoundError:
    print("WARNING: pbp_situation_features.json not found. PBP model inference may fail.")
    pbp_feature_columns = []


@app.route("/", methods=['GET'])
def home():
    return "<h1>DigitalOC Tendency Scouting Server is Live</h1>"


@app.route("/suggestPlay", methods=['POST'])
def suggest_play():
    """ 
    Endpoint returning opponent play-calling tendencies based on game state, 
    personnel, and historical sequences. 
    """
    data = request.get_json()
    current_situation = data.get('current_situation', {})
    play_history = data.get('play_history', []) 
    
    yardline = current_situation.get('yardline_100', 50)
    score_diff = current_situation.get('score_differential', 0)
    
    if abs(score_diff) > 16:
        print("NOTICE: Game state is non-competitive. Tendencies may be skewed by clock-management.")

    # Calculate sequence features dynamically from history
    prev_is_pass = prev_is_run = prev_yards_gained = 0
    two_consecutive_runs = two_consecutive_passes = 0
    
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

    # Unified Situation Dictionary mapped to training schema
    situation_dict = {
        "down": current_situation.get('down', 1),
        "ydstogo": current_situation.get('ydstogo', 10),
        "yardline_100": yardline,
        "goal_to_go": current_situation.get('goal_to_go', 0),
        "quarter_seconds_remaining": current_situation.get('quarter_seconds_remaining', 900),
        "half_seconds_remaining": current_situation.get('half_seconds_remaining', 1800),
        "game_seconds_remaining": current_situation.get('game_seconds_remaining', 3600),
        "score_differential": score_diff,
        "posteam_timeouts_remaining": current_situation.get('posteam_timeouts_remaining', 3),
        "defteam_timeouts_remaining": current_situation.get('defteam_timeouts_remaining', 3),
        "posteam": current_situation.get('posteam', 'UNK'),
        "defteam": current_situation.get('defteam', 'UNK'),
        "offense_personnel": current_situation.get('offense_personnel', '11'),
        "offense_formation": current_situation.get('offense_formation', 'SHOTGUN'),
        "prev_is_pass": prev_is_pass,
        "prev_is_run": prev_is_run,
        "prev_yards_gained": prev_yards_gained,
        "two_consecutive_runs": two_consecutive_runs,
        "two_consecutive_passes": two_consecutive_passes,
    }

    # 1. ROOT SITUATION: Run vs. Pass Probability
    pbp_report = predict_play(situation_dict, pbp_model, pbp_feature_columns)
    primary_tendency = pbp_report['primary_tendency'].lower()
    
    scouting_report = {
        "pbp_tendency": pbp_report,
        "run_tendencies": None,
        "pass_tendencies": None
    }
    
    play_visualization = None

    # 2A. RUN TENDENCY PREDICTION
    if primary_tendency == 'run':
        run_predictions = predict_run_metrics(situation_dict, run_models)
        scouting_report["run_tendencies"] = run_predictions
        
        # Grab the top probability run lane for visualization
        top_run = run_predictions["run_tendencies"][0]
        run_loc = top_run["run_location"]
        run_gap = top_run["run_gap"]
        
        # Update the personnel filter to have a fallback
        raw_personnel = situation_dict["offense_personnel"]
        personnel_rb_wr_te = ', '.join([
            part for part in raw_personnel.split(', ') 
            if any(pos in part for pos in ['RB', 'WR', 'TE'])
        ])
        if not personnel_rb_wr_te:
            personnel_rb_wr_te = raw_personnel  # Fallback to the raw string if filter fails

        run_play_input = {
            "play_type": "run",                   # <--- ADD THIS
            "yardline_100": yardline,
            "down": situation_dict["down"],
            "ydstogo": situation_dict["ydstogo"],
            "pass_length": None,
            "pass_location": None, 
            "air_yards": None, 
            "run_location": run_loc,
            "run_gap": run_gap,
            "rusher": 'N/A', 
            "receiver": None, 
            "offense_formation": situation_dict["offense_formation"],
            "offense_personnel": personnel_rb_wr_te,
            "route": None,
            "involved_player_position": "RB",
            "posteam": situation_dict["posteam"],
            "defteam": situation_dict["defteam"]
        }
        
        play_visualization = visualize_play(run_play_input)

    # 2B. PASS TENDENCY PREDICTION
    elif primary_tendency == 'pass':
        pass_predictions = predict_pass_metrics(situation_dict, pass_models)
        scouting_report["pass_tendencies"] = pass_predictions
        
        # Grab top targets for visualization
        top_target_area = pass_predictions['pass_target_area'][0]['label']
        top_route = pass_predictions['route'][0]['label']
        top_receiver = pass_predictions['receiver_position'][0]['label']
        
        if "_" in top_target_area:
            p_length, p_loc = top_target_area.split("_", 1)
        else:
            p_length, p_loc = top_target_area, None

        pass_play_input = {
            "play_type": "pass",                  # <--- ADD THIS
            "yardline_100": yardline,
            "down": situation_dict["down"],
            "ydstogo": situation_dict["ydstogo"],
            "pass_length": p_length,
            "pass_location": p_loc,
            "air_yards": 10,
            "run_location": None,
            "run_gap": None,
            "rusher": None,
            "receiver": 'N/A',
            "offense_formation": situation_dict["offense_formation"],
            "offense_personnel": situation_dict["offense_personnel"],
            "route": top_route,
            "involved_player_position": top_receiver,
            "posteam": situation_dict["posteam"],
            "defteam": situation_dict["defteam"]
        }
        
        play_visualization = visualize_play(pass_play_input)

    # Encode drawing to base64
    play_visualization_b64 = None
    if play_visualization:
        play_visualization_b64 = base64.b64encode(play_visualization.getvalue()).decode('utf-8')
        plt.close() # Clean up memory

    return jsonify({
        "scouting_report": scouting_report,
        "play_visualization": play_visualization_b64
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000, host='0.0.0.0', use_reloader=False)
