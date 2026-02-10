from flask import Flask, jsonify, send_file
from flask_cors import CORS
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for Flask
import matplotlib.pyplot as plt

from pbp_situation_model import train_pbp_model, predict_play
from run_model import train_run_models, predict_run_metrics
from pass_model import train_pass_models, predict_pass_metrics
from routeDrawer.playDraw import visualize_play


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# Global variables to store loaded models
pbp_model = None
pbp_feature_columns = None
run_models = None
pass_models = None


def train_all_models():
    """Train all models on application startup."""
    global pbp_model, pbp_feature_columns, run_models, pass_models
    
    print("=" * 60)
    print("Training models on Flask app startup...")
    print("=" * 60)
    print()
    
    # Train PBP model
    print("1. Training PBP (Play-by-Play) model...")
    print("-" * 60)
    try:
        pbp_model, pbp_feature_columns = train_pbp_model()
        print("✓ PBP model trained successfully")
    except Exception as e:
        print(f"✗ Error training PBP model: {e}")
        raise
    print()
    
    # Train Run models
    print("2. Training Run models...")
    print("-" * 60)
    try:
        run_models = train_run_models()
        if run_models:
            print("✓ Run models trained successfully")
        else:
            print("✗ Run model training returned empty dictionary")
    except Exception as e:
        print(f"✗ Error training Run models: {e}")
        raise
    print()
    
    # Train Pass model
    print("3. Training Pass model...")
    print("-" * 60)
    try:
        from pass_model import train_pass_models
        pass_models = train_pass_models()
        if pass_models:
            print("✓ Pass models trained successfully")
        else:
            print("✗ Pass model training returned empty dictionary")
    except Exception as e:
        print(f"✗ Error training Pass model: {e}")
        # Don't raise for pass model since it's optional
    print()
    
    print("=" * 60)
    print("Model training complete! Flask app is ready.")
    print("=" * 60)
    print()


# Train all models when the application starts
train_all_models() 


@app.route("/suggestPlay/<situation>", methods=['GET'])
def suggest_play(situation):
    ''' Endpoint from the React frontend to get play suggestion based on the incoming situation '''


    # Convert the attributes from the URL string to a list of appropriate types
    '''
        The string is as follows:

        "down [0], ydstogo [1], yardline_100 [2], goal_to_go [3], quarter_seconds_remaining [4], half_seconds_remaining [5], 
        game_seconds_remaining [6], score_differential [7], posteam_timeouts_remaining [8], defteam_timeouts_remaining [9], 
        posteam [10], defteam [11]"
    '''
    situation = situation.split(',')
    situation = [int(situation[0]), int(situation[1]), int(situation[2]), int(situation[3]), int(situation[4]),
                 int(situation[5]), int(situation[6]), int(situation[7]), int(situation[8]), int(situation[9]),
                 situation[10], situation[11]]


    # Predict whether the play type for the given situation should be a run or pass
    prediction, confidence = predict_play(situation, trained_model=pbp_model, feature_columns=pbp_feature_columns)


    # Depending on the prediction, feed it into the run or pass model
    if prediction == 'run':
        run_prediction = predict_run_metrics(situation, trained_models=run_models)
        run_gap = run_prediction.get('run_gap', 'unknown')
        run_location = run_prediction.get('run_location')
        offense_formation = run_prediction.get('offense_formation')
        personnel_off = run_prediction.get('personnel_off')

        print(f"Suggested Run Play Metrics")
        print(f"Run Gap: {run_gap}")
        print(f"Run Location: {run_location}")
        print(f"Offense Formation: {offense_formation}")
        print(f"Personnel Offense: {personnel_off}")

        # Modify the offense personnel to get only the RBs, WRs, and TEs when visualizing the play
        if personnel_off is not None:
            personnel_parts = personnel_off.split(', ')
            personnel_rb_wr_te = ', '.join([part for part in personnel_parts if any(pos in part for pos in ['RB', 'WR', 'TE'])])
        else:
            personnel_rb_wr_te = "Personnel Unknown"
        print(f"Personnel (RB/WR/TE only): {personnel_rb_wr_te}")

        run_play_input = {
            "yardline_100": situation[2],
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
            "involved_player_position": "RB"
        }

        # Play visualization will be saved to play_visualization.png
        visualize_play(run_play_input)


    elif prediction == 'pass':
        pass_prediction = predict_pass_metrics(situation, trained_models=pass_models)
        pass_length = pass_prediction['pass_length']
        pass_location = pass_prediction['pass_location']
        offense_formation = pass_prediction['offense_formation']
        offense_personnel = pass_prediction['offense_personnel']
        route = pass_prediction['route']
        receiver_position = pass_prediction['receiver_position']

        print(f"Pass Prediction Metrics:")
        print(f"Pass Length: {pass_length}")
        print(f"Pass Location: {pass_location}")
        print(f"Offense Formation: {offense_formation}")
        print(f"Offense Personnel: {offense_personnel}")
        print(f"Route: {route}")
        print(f"Receiver Position: {receiver_position}")

        pass_play_input = {
            "yardline_100": situation[2],
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
            "involved_player_position": receiver_position
        }

        # Play visualization will be saved to play_visualization.png
        visualize_play(pass_play_input)

    else:
        print("Unknown play type prediction.")

    return "Success"


@app.route("/playVisualization", methods=['GET'])
def get_play_visualization():
    return send_file('play_visualization.png', mimetype='image/png')


if __name__ == "__main__":
    app.run()