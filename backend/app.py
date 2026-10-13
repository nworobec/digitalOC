import base64
import io
import hashlib
import math
from flask import Flask, jsonify, request, g
from flask_cors import CORS
import joblib
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for Flask
import matplotlib.pyplot as plt
import urllib.request

from model_trainers.pbp_situation_model import predict_play
from model_trainers.run_model import predict_run_metric_candidates
from model_trainers.pass_model import predict_pass_metric_candidates
from model_trainers.exp_run_yards_model import predict_exp_yards_run
from model_trainers.exp_pass_yards_model import predict_exp_yards_pass
from routeDrawer.playDraw import visualize_play
from request_logging import install_request_logging


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, expose_headers=["X-Request-ID"])
model_versions = {}
install_request_logging(app, model_versions)


# Load the PBP, run, pass, and expected yards models from GitHub Releases when the application starts
def load_model_from_url(url: str):
    with urllib.request.urlopen(url, timeout=60) as response:
        content = response.read()
        buffer = io.BytesIO(content)
    model_versions[url.rsplit("/", 1)[-1]] = hashlib.sha256(content).hexdigest()[:16]
    return joblib.load(buffer)

BASE_URL = "https://github.com/nworobec/digitalOC/releases/download"

pbp_model = load_model_from_url(f"{BASE_URL}/pbp-model/pbp_situation_model.joblib")
run_models = load_model_from_url(f"{BASE_URL}/run-model/run_model.joblib")
pass_models = load_model_from_url(f"{BASE_URL}/pass-model/pass_model.joblib")
exp_run_yards_model = load_model_from_url(f"{BASE_URL}/exp-run-yards-model/exp_run_yards_model.joblib")
completion_prob_model = load_model_from_url(f"{BASE_URL}/completion-prob-model/completion_prob_model.joblib")
exp_pass_yards_model = load_model_from_url(f"{BASE_URL}/exp-pass-yards-model/exp_pass_yards_model.joblib")


@app.route("/", methods=["GET"])
def home():
    return "<h1>Server is working</h1>"


def to_scalar(value, cast_type=float):
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        while isinstance(value, (list, tuple)) and len(value) > 0:
            value = value[0]
    return cast_type(value)


@app.route("/suggestPlay", methods=["POST"])
def suggest_play():
    """
    Endpoint from the React frontend to get play suggestions
    based on the incoming situation and play history.
    Returns top 3 suggested plays instead of only 1.
    """

    data = request.get_json()
    if not isinstance(data, dict):
        return jsonify({"error": "Expected a JSON object"}), 400
    current_situation = data.get("current_situation", {})
    play_history = data.get("play_history", [])
    if not isinstance(current_situation, dict) or not isinstance(play_history, list):
        return jsonify({"error": "current_situation must be an object and play_history a list"}), 400
    numeric_fields = ["down", "ydstogo", "yardline_100", "goal_to_go", "quarter_seconds_remaining",
                      "half_seconds_remaining", "game_seconds_remaining", "score_differential",
                      "posteam_timeouts_remaining", "defteam_timeouts_remaining"]
    for field in numeric_fields:
        if field in current_situation:
            value = current_situation[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return jsonify({"error": f"{field} must be a finite number"}), 400
    for play in play_history:
        if (not isinstance(play, dict) or play.get("play_type") not in ("run", "pass")
                or isinstance(play.get("yards_gained"), bool)
                or not isinstance(play.get("yards_gained"), (int, float))
                or not math.isfinite(play["yards_gained"])):
            return jsonify({"error": "Each history entry needs a run/pass play_type and finite yards_gained"}), 400

    yardline = current_situation.get("yardline_100", 50)
    score_diff = current_situation.get("score_differential", 0)

    if abs(score_diff) > 16:
        print("NOTICE: Game state is non-competitive. Suggestion may be biased by clock-management.")

    is_midfield_aggression = 1 if 35 <= yardline <= 45 else 0
    is_deep_redzone = 1 if yardline <= 10 else 0

    # Sequence features from prior plays
    prev_is_pass = 0
    prev_is_run = 0
    prev_yards_gained = 0
    two_consecutive_runs = 0
    two_consecutive_passes = 0

    if len(play_history) > 0:
        last_play = play_history[-1]
        prev_is_pass = 1 if last_play.get("play_type") == "pass" else 0
        prev_is_run = 1 if last_play.get("play_type") == "run" else 0
        prev_yards_gained = last_play.get("yards_gained", 0)

    if len(play_history) >= 2:
        last_play = play_history[-1]
        two_plays_ago = play_history[-2]

        if last_play.get("play_type") == "run" and two_plays_ago.get("play_type") == "run":
            two_consecutive_runs = 1

        if last_play.get("play_type") == "pass" and two_plays_ago.get("play_type") == "pass":
            two_consecutive_passes = 1

    # Situation format expected by the models
    situation = [
        current_situation.get("down", 1),
        current_situation.get("ydstogo", 10),
        yardline,
        current_situation.get("goal_to_go", 0),
        current_situation.get("quarter_seconds_remaining", 900),
        current_situation.get("half_seconds_remaining", 1800),
        current_situation.get("game_seconds_remaining", 3600),
        score_diff,
        current_situation.get("posteam_timeouts_remaining", 3),
        current_situation.get("defteam_timeouts_remaining", 3),
        current_situation.get("posteam", "UNK"),
        current_situation.get("defteam", "UNK"),
        is_midfield_aggression,
        is_deep_redzone,
        prev_is_pass,
        prev_is_run,
        prev_yards_gained,
        two_consecutive_runs,
        two_consecutive_passes,
        current_situation.get("defense_coverage_type", "UNKNOWN")
    ]
    g.processed_situation = dict(zip([
        "down", "ydstogo", "yardline_100", "goal_to_go", "quarter_seconds_remaining",
        "half_seconds_remaining", "game_seconds_remaining", "score_differential",
        "posteam_timeouts_remaining", "defteam_timeouts_remaining", "posteam", "defteam",
        "is_midfield_aggression", "is_deep_redzone", "prev_is_pass", "prev_is_run",
        "prev_yards_gained", "two_consecutive_runs", "two_consecutive_passes", "defense_coverage_type"
    ], situation))
    g.history_length = len(play_history)

    # Predict whether the play type should be a run or pass
    forced_play = current_situation.get('forced_play_type')

    if forced_play:
        if not isinstance(forced_play, str) or forced_play.lower() not in ("run", "pass"):
            return jsonify({"error": "forced_play_type must be run or pass"}), 400
        print(f"COACH OVERRIDE ACTIVATED: Forcing a {forced_play.upper()}")
        prediction = forced_play.lower()
        confidence = None
    else:
        # Predict whether the play type should be a run or pass
        prediction_int, confidence_raw = predict_play(situation, trained_model=pbp_model)
        prediction_int = to_scalar(prediction_int, int)

        # 1 = Pass Intent (Passes, Sacks, Scrambles), 0 = Run Intent
        prediction = 'pass' if prediction_int == 1 else 'run'
        selected_class_index = list(pbp_model.classes_).index(prediction_int)
        confidence = float(confidence_raw[selected_class_index])
    
    play_outputs = []

    if prediction == "run":
        run_predictions = predict_run_metric_candidates(
            situation,
            trained_models=run_models,
            top_k=3
        )

        for idx, run_prediction in enumerate(run_predictions, start=1):
            run_gap = run_prediction["run_gap"]
            run_location = run_prediction["run_location"]
            offense_formation = run_prediction["offense_formation"]
            personnel_off = run_prediction["personnel_off"]

            personnel_rb_wr_te = ", ".join([
                part for part in personnel_off.split(", ")
                if any(pos in part for pos in ["RB", "WR", "TE"])
            ])

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

            exp_yards = str(
                predict_exp_yards_run(run_play_input, exp_run_yards_model).round(2)
            )

            play_visualization = visualize_play(run_play_input)
            play_visualization_b64 = base64.b64encode(
                play_visualization.getvalue()
            ).decode("utf-8")

            play_outputs.append({
                "rank": idx,
                "play_type": "run",
                "confidence": float(run_prediction.get("confidence", 0.0)),
                "expected_yards": exp_yards,
                "play_visualization": play_visualization_b64,
                "play_data": {
                    "run_gap": run_gap,
                    "run_location": run_location,
                    "offense_formation": offense_formation,
                    "personnel_off": personnel_off
                }
            })

    elif prediction == "pass":
        pass_predictions = predict_pass_metric_candidates(
            situation,
            trained_models=pass_models,
            top_k=3
        )

        for idx, pass_prediction in enumerate(pass_predictions, start=1):
            pass_length = pass_prediction["pass_length"]
            pass_location = pass_prediction["pass_location"]
            offense_formation = pass_prediction["offense_formation"]
            offense_personnel = pass_prediction["offense_personnel"]
            route = pass_prediction["route"]
            receiver_position = pass_prediction["receiver_position"]

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

            p_complete_and_exp_yards = predict_exp_yards_pass(
                pass_play_input,
                completion_prob_model,
                exp_pass_yards_model
            )

            exp_yards = (
                f"{p_complete_and_exp_yards[0].round(2)}\n"
                f"({(p_complete_and_exp_yards[1] * 100).round(0)}% will be complete)"
            )

            play_visualization = visualize_play(pass_play_input)
            play_visualization_b64 = base64.b64encode(
                play_visualization.getvalue()
            ).decode("utf-8")

            play_outputs.append({
                "rank": idx,
                "play_type": "pass",
                "confidence": float(pass_prediction.get("confidence", 0.0)),
                "expected_yards": exp_yards,
                "play_visualization": play_visualization_b64,
                "play_data": {
                    "pass_length": pass_length,
                    "pass_location": pass_location,
                    "offense_formation": offense_formation,
                    "offense_personnel": offense_personnel,
                    "route": route,
                    "receiver_position": receiver_position
                }
            })

    return jsonify({
        "request_id": g.request_id,
        "model_versions": model_versions,
        "play_type": prediction,
        "model_confidence": confidence,
        "plays": play_outputs
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000, host='0.0.0.0', use_reloader=False)
