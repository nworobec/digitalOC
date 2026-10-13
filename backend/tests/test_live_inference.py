import contextlib
import io
import json
import unittest

import numpy as np
import pandas as pd
from flask import Flask
from sklearn.preprocessing import StandardScaler

from backend.model_trainers.inference import encode_inference, align_inference
from backend.model_trainers.pass_model import predict_pass_metric_candidates
from backend.model_trainers.run_model import predict_run_metric_candidates
from backend.request_logging import install_request_logging


SITUATION = [2, 6, 45, 0, 300, 300, 2100, 0, 3, 3, 'KC', 'BUF', 0, 0, 1, 0, 5, 0, 0, 'COVER_3']


class RecordingModel:
    def __init__(self, classes):
        self.classes_ = np.array(classes)
        self.inputs = []

    def predict_proba(self, frame):
        self.inputs.append(frame)
        return np.tile(np.array([0.7, 0.3]), (len(frame), 1))


class LiveInferenceTests(unittest.TestCase):
    def test_single_row_matches_training_encoding_including_reference_category(self):
        raw = pd.DataFrame({'posteam': ['ARI', 'KC'], 'defteam': ['ARI', 'BUF'],
                            'defense_coverage_type': ['COVER_1', 'COVER_3'], 'down': [1, 2]})
        training = pd.get_dummies(raw, drop_first=True)
        for index in (0, 1):
            single = align_inference(encode_inference(raw.iloc[[index]]), training.columns, 'test')
            pd.testing.assert_frame_equal(single, training.iloc[[index]], check_dtype=False)

    def test_pass_candidates_preserve_coverage_and_teams(self):
        columns = ['posteam_KC', 'defteam_BUF', 'defense_coverage_type_COVER_3', 'down']
        models = {target: {'model': RecordingModel(['first', 'second']), 'feature_columns': columns}
                  for target in ['pass_length', 'pass_location', 'route', 'receiver_position',
                                 'offense_formation', 'offense_personnel']}
        with contextlib.redirect_stdout(io.StringIO()):
            plays = predict_pass_metric_candidates(SITUATION, models)
        self.assertEqual(len(plays), 2)
        self.assertEqual(models['route']['model'].inputs[0].iloc[0].tolist(), [True, True, True, 2])

    def test_run_candidates_apply_saved_scaler_and_bound_candidate_count(self):
        columns = ['posteam_KC', 'defteam_BUF', 'defense_coverage_type_COVER_3', 'ydstogo']
        scaler = StandardScaler().fit(pd.DataFrame([[0, 0, 0, 2], [1, 1, 1, 10]], columns=columns))
        models = {target: {'model': RecordingModel(['first', 'second']), 'columns': columns, 'scaler': scaler}
                  for target in ['run_gap', 'run_location', 'offense_formation', 'personnel_off']}
        plays = predict_run_metric_candidates(SITUATION, models, top_k=3)
        self.assertEqual(len(plays), 2)
        np.testing.assert_allclose(models['run_gap']['model'].inputs[0], [[1, 1, 1, 0]])
        with self.assertRaisesRegex(ValueError, 'Missing predictions'):
            predict_run_metric_candidates(SITUATION, {})

    def test_request_ids_correlate_success_error_and_actual_model_inputs(self):
        app = Flask(__name__)
        install_request_logging(app, {'fixture': 'abc123'})

        @app.get('/success')
        def success():
            align_inference(encode_inference(pd.DataFrame([{'posteam': 'KC', 'down': 2}])),
                            ['posteam_KC', 'down'], 'fixture')
            return {'play_type': 'pass', 'plays': [{}]}

        @app.get('/failure')
        def failure():
            raise RuntimeError('Internal failure details')

        with self.assertLogs('digitaloc.requests', level='INFO') as captured:
            success_response = app.test_client().get('/success')
            failure_response = app.test_client().get('/failure')
        entries = [json.loads(record.getMessage()) for record in captured.records
                   if json.loads(record.getMessage())['event'] == 'request_completed']
        self.assertEqual(success_response.headers['X-Request-ID'], entries[0]['request_id'])
        self.assertEqual(entries[0]['model_inputs'][0]['active_categories'], ['posteam_KC'])
        self.assertEqual(entries[0]['model_versions'], {'fixture': 'abc123'})
        self.assertEqual(failure_response.status_code, 500)
        self.assertEqual(failure_response.json['request_id'], entries[1]['request_id'])
        self.assertNotEqual(entries[0]['request_id'], entries[1]['request_id'])
        self.assertNotIn('Internal failure details', failure_response.json['error'])


if __name__ == '__main__':
    unittest.main()
