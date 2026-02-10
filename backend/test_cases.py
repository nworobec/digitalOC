''' 
    Test cases only
'''

# import io
# import base64
# import matplotlib
# matplotlib.use('Agg')  # Use non-interactive backend for server
# import matplotlib.pyplot as plt

from pbp_situation_model import train_pbp_situation_model, predict_play
from run_model import train_run_models, predict_run_metrics
from pass_model import train_pass_models, predict_pass_metrics
from routeDrawer.playDraw import visualize_play


if __name__ == "__main__":
    # Test situations to predict play type - [down, ydstogo, yardline_100, goal_to_go, quarter_seconds_remaining, half_seconds_remaining, game_seconds_remaining, score_differential, posteam_timeouts_remaining, defteam_timeouts_remaining, posteam, defteam]
    # test_case_1 = [2, 5, 30, 0, 720, 720, 2520, 0, 3, 3, 'KC', 'BUF'] # 2nd & 5 from opponent's 30-yard line, Q2-12:00, tied game, balanced situation
    test_case_2 = [3, 8, 50, 0, 180, 1080, 1080, -3, 2, 3, 'GB', 'DAL'] # 3rd & 8 from midfield, Q3-3:00, down by 3, passing situation
    # test_case_3 = [1, 10, 75, 0, 480, 1380, 3180, 7, 3, 3, 'SF', 'SEA'] # 1st & 10 from own 25-yard line, Q1-8:00, ahead by 7, balanced situation
    # test_case_4 = [1, 8, 8, 1, 95, 95, 95, -4, 1, 2, 'NE', 'NYG'] # 1st & Goal from 8-yard line, Q4-1:35, down by 4, red zone situation  
    # test_case_5 = [4, 2, 35, 0, 45, 45, 45, -6, 0, 1, 'TB', 'DET'] # 4th & 2 from opponent's 35, Q4-0:45, down by 6, desperation situation
    # test_case_6 = [3, 1, 60, 0, 600, 1500, 3300, 0, 2, 2, 'MIA', 'NYJ'] # 3rd & 1 from own 40, Q1-10:00, tied game, short yardage situation
    # test_case_7 = [1, 1, 1, 1, 600, 600, 2400, 0, 2, 2, 'PHI', 'LAR'] # 1st & Goal from the 1, Q3-10:00, Tush Push Situation for the Eagles 
    # test_case_8 = [3, 15, 80, 0, 900, 900, 900, -10, 1, 2, 'CIN', 'PIT'] # 3rd and long from own 20, Q4-15:00, down by 10, passing situation

    # all_test_cases = [test_case_1, test_case_2, test_case_3, test_case_4, test_case_5, test_case_6, test_case_7, test_case_8]

    all_test_cases = [test_case_2]

    # Load the PBP Situation, Run, and Pass models


    ''' Predict whether the play for the given situation should be a run or pass '''

    # Train the PBP Situation Model
    pbp_situation_model, feature_columns = train_pbp_situation_model()
    print(feature_columns)
    print()

    # Train the Run Models 
    all_run_models = train_run_models()

    # Train the Pass Models
    all_pass_models = train_pass_models()


    for test_case in all_test_cases:
        # Predict the most optimal play for each situation
        prediction, confidence = predict_play(test_case, pbp_situation_model, feature_columns)

        ''' 
            From this point on, depending on the predicition, you would either feed it into the run or pass model. 

            Just like the PBP model, build the run/pass models in separate files and then import them here.
        '''

        if prediction == 'run':
            run_prediction = predict_run_metrics(test_case, all_run_models)
            run_gap = run_prediction['run_gap']
            run_location = run_prediction['run_location']
            offense_formation = run_prediction['offense_formation']
            personnel_off = run_prediction['personnel_off']

            print(f"Suggested Run Play Metrics")
            print(f"Run Gap: {run_gap}")
            print(f"Run Location: {run_location}")
            print(f"Offense Formation: {offense_formation}")
            print(f"Personnel Offense: {personnel_off}")

            # Modify the offense personnel to get only the RBs, WRs, and TEs when visualizing the play
            personnel_rb_wr_te = ', '.join([part for part in personnel_off.split(', ') if any(pos in part for pos in ['RB', 'WR', 'TE'])])
            print(f"Personnel (RB/WR/TE only): {personnel_rb_wr_te}")

            run_play_input = {
                "yardline_100": test_case[2],
                "down": test_case[0],
                "ydstogo": test_case[1],
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

            visualize_play(run_play_input)

        elif prediction == 'pass':
            pass_prediction = predict_pass_metrics(test_case, all_pass_models)
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
                "yardline_100": test_case[2],
                "down": test_case[0],
                "ydstogo": test_case[1],
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

            visualize_play(pass_play_input)

        else:
            print("Unknown play type")
    