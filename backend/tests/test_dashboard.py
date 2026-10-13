import copy
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend.decision_support.api import create_app
from backend.decision_support.game import DEFAULT_STATE, advance_play


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "sessions.sqlite"
        self.app = create_app(Path(self.directory.name) / "absent.joblib", db_path=self.db, data_dir=self.directory.name)
        self.client = self.app.test_client()
        self.state = {**DEFAULT_STATE, "yardline_100": 45, "down": 2, "ydstogo": 6}
        response = self.client.post('/api/sessions', json={'state': self.state})
        self.assertEqual(response.status_code, 201)
        self.session = response.get_json()
        self.url = '/api/sessions/' + self.session['id']

    def payload(self, **values):
        return dict(revision=self.session['revision'], mutation_id=uuid.uuid4().hex, **values)

    def save_response(self, response):
        self.assertEqual(response.status_code, 200, response.get_json())
        self.session = response.get_json()
        return self.session

    def test_resume_session_from_another_app_instance(self):
        client = create_app(Path(self.directory.name) / 'absent', db_path=self.db).test_client()
        self.assertEqual(client.get(self.url).get_json()['state'], self.state)
        self.assertEqual(len(client.get('/api/sessions').get_json()['sessions']), 1)

    def test_queue_is_not_a_completed_play(self):
        queued = self.save_response(self.client.post(self.url + '/queue', json=self.payload(call_id='mesh')))
        self.assertEqual(len(queued['queue']), 1)
        self.assertEqual(queued['plays'], [])
        self.assertEqual(queued['state'], self.state)

    def test_record_consume_queue_advance_and_undo(self):
        self.save_response(self.client.post(self.url + '/queue', json=self.payload(call_id='mesh')))
        queue_id = self.session['queue'][0]['id']
        self.save_response(self.client.post(self.url + '/plays', json=self.payload(
            call_id='mesh', queue_id=queue_id,
            outcome=dict(kind='gain', yards=7, elapsed_seconds=18, observed_coverage='COVER_3'))))
        self.assertEqual(self.session['state']['yardline_100'], 38)
        self.assertEqual(self.session['state']['down'], 1)
        self.assertEqual(self.session['state']['ydstogo'], 10)
        self.assertEqual(self.session['state']['quarter_seconds_remaining'], 882)
        self.assertEqual(self.session['queue'], [])
        self.assertTrue(self.session['can_undo'])
        self.save_response(self.client.post(self.url + '/undo', json=self.payload()))
        self.assertEqual(self.session['state'], self.state)
        self.assertEqual(self.session['queue'][0]['id'], queue_id)
        self.assertEqual(self.session['plays'], [])

    def test_duplicate_mutation_does_not_record_twice(self):
        payload = self.payload(call_id='zone', outcome=dict(kind='gain', yards=2, elapsed_seconds=5))
        first = self.client.post(self.url + '/plays', json=payload).get_json()
        second = self.client.post(self.url + '/plays', json=payload).get_json()
        self.assertEqual(first, second)
        self.assertEqual(len(second['plays']), 1)
        altered = copy.deepcopy(payload)
        altered['outcome']['yards'] = 3
        self.assertEqual(self.client.post(self.url + '/plays', json=altered).status_code, 409)

    def test_stale_revision_cannot_overwrite_state(self):
        stale = self.payload(state={**self.state, 'down': 4})
        self.save_response(self.client.patch(self.url, json=self.payload(state={**self.state, 'down': 3})))
        self.assertEqual(self.client.patch(self.url, json=stale).status_code, 409)
        self.assertEqual(self.client.get(self.url).get_json()['state']['down'], 3)

    def test_illegal_outcome_is_atomic(self):
        response = self.client.post(self.url + '/plays', json=self.payload(
            call_id='mesh', outcome=dict(kind='touchdown', yards=2, elapsed_seconds=5)))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(self.url).get_json()['revision'], 0)
        self.assertEqual(self.client.get(self.url).get_json()['plays'], [])

    def test_touchdown_stops_evaluation_until_new_drive(self):
        self.save_response(self.client.post(self.url + '/plays', json=self.payload(
            call_id='mesh', outcome=dict(kind='touchdown', yards=45, elapsed_seconds=9))))
        self.assertEqual(self.session['state']['offense_score'], 6)
        self.assertEqual(self.session['status'], 'awaiting_drive')
        self.assertEqual(self.client.get(self.url + '/evaluation').get_json()['status'], 'awaiting_drive')
        self.assertEqual(self.client.post(self.url + '/queue', json=self.payload(call_id='zone')).status_code, 400)
        next_state = {**DEFAULT_STATE, 'posteam': 'BUF', 'defteam': 'KC', 'defense_score': 7}
        self.save_response(self.client.post(self.url + '/drive', json=self.payload(state=next_state)))
        self.assertEqual(self.session['drive'], 2)
        self.assertEqual(self.session['status'], 'active')
        self.assertEqual(len(self.session['plays']), 1)

    def test_observation_edit_has_no_fake_history_and_no_fake_forecast(self):
        self.save_response(self.client.patch(self.url, json=self.payload(state={**self.state, 'coverage': 'MAN'})))
        self.assertEqual(self.session['plays'], [])
        result = self.client.get(self.url + '/evaluation').get_json()
        self.assertEqual(result['status'], 'model_unavailable')
        self.assertIsNone(result['conversion_probability'])
        self.assertIsNone(result['comparison'])
        self.assertEqual(result['defense']['status'], 'unavailable')

    def test_constraint_and_unknown_call_validation(self):
        self.save_response(self.client.patch(self.url, json=self.payload(state={**self.state, 'action_filter': 'run'})))
        self.assertEqual(self.client.post(self.url + '/queue', json=self.payload(call_id='mesh')).status_code, 400)
        self.assertEqual(self.client.post(self.url + '/queue', json=self.payload(call_id='nonexistent')).status_code, 400)
        self.assertEqual(self.client.post(self.url + '/queue', json=self.payload(call_id='zone')).status_code, 200)

    def test_invalid_game_state_and_request_trace(self):
        for replacement in [{'ydstogo': 80}, {'quarter_seconds_remaining': 901}, {'down': True}, {'posteam': 'BUF'}]:
            response = self.client.patch(self.url, json=self.payload(state={**self.state, **replacement}))
            self.assertEqual(response.status_code, 400)
            self.assertTrue(response.headers.get('X-Request-ID'))

    def test_what_if_evaluation_never_writes_history(self):
        bundle = {'schema_version': 1, 'teams': ['KC', 'BUF'], 'model_id': 'test'}
        client = create_app(bundle=bundle, db_path=self.db, data_dir=self.directory.name).test_client()
        with patch('backend.decision_support.dashboard.compare_options', return_value={'options': []}) as compare:
            response = client.get(self.url + '/evaluation')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()['branches']), 2)
        self.assertEqual(compare.call_count, 3)
        self.assertEqual(client.get(self.url).get_json()['revision'], 0)
        self.assertEqual(client.get(self.url).get_json()['plays'], [])


class TransitionTests(unittest.TestCase):
    def test_loss_and_failed_fourth_down(self):
        state = {**DEFAULT_STATE, 'down': 3, 'ydstogo': 4, 'yardline_100': 48}
        after, status = advance_play(state, dict(kind='sack', yards=-6, elapsed_seconds=12))
        self.assertEqual((after['down'], after['ydstogo'], after['yardline_100'], status), (4, 10, 54, 'active'))
        _, status = advance_play(after, dict(kind='incomplete', yards=0, elapsed_seconds=3))
        self.assertEqual(status, 'awaiting_drive')

    def test_halftime_resets_timeouts_and_stops_drive(self):
        state = {**DEFAULT_STATE, 'qtr': 2, 'quarter_seconds_remaining': 12, 'posteam_timeouts_remaining': 0}
        after, status = advance_play(state, dict(kind='gain', yards=3, elapsed_seconds=12))
        self.assertEqual((after['qtr'], after['quarter_seconds_remaining'], after['posteam_timeouts_remaining'], status), (3, 900, 3, 'awaiting_drive'))

    def test_end_regulation_and_turnover(self):
        _, status = advance_play({**DEFAULT_STATE, 'qtr': 4, 'quarter_seconds_remaining': 3}, dict(kind='gain', yards=0, elapsed_seconds=3))
        self.assertEqual(status, 'finished')
        _, status = advance_play(DEFAULT_STATE, dict(kind='turnover', yards=0, elapsed_seconds=5))
        self.assertEqual(status, 'awaiting_drive')

    def test_safety_and_invalid_clock(self):
        after, status = advance_play({**DEFAULT_STATE, 'yardline_100': 95}, dict(kind='safety', yards=-5, elapsed_seconds=5))
        self.assertEqual(after['defense_score'], 2)
        self.assertEqual(status, 'awaiting_drive')
        with self.assertRaises(ValueError):
            advance_play(DEFAULT_STATE, dict(kind='gain', yards=1, elapsed_seconds=901))


if __name__ == '__main__':
    unittest.main()
