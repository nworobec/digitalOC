import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from backend.decision_support.api import create_app
from backend.decision_support.game import DEFAULT_STATE, COVERAGES
from backend.decision_support.playbook import PLAYBOOK, default_preferences, validate_preferences
from backend.decision_support.suitability import suggest_concepts


class FitTests(unittest.TestCase):
    def test_distance_and_coverage_change_shortlist_deterministically(self):
        def ids(state, preferences=None):
            return [p['call_id'] for p in suggest_concepts({**DEFAULT_STATE, **state}, preferences)['suggestions']]
        short = ids(dict(down=3, ydstogo=1))
        long = ids(dict(down=3, ydstogo=15))
        self.assertIn('power', short)
        self.assertIn('verticals', long)
        self.assertNotEqual(short, long)
        self.assertEqual(long, ids(dict(down=3, ydstogo=15)))
        self.assertNotEqual(ids(dict(ydstogo=5), {**default_preferences(), 'anticipated_coverage': 'MAN'}),
                            ids(dict(ydstogo=5), {**default_preferences(), 'anticipated_coverage': 'ZONE'}))

    def test_hard_constraints_and_no_fabricated_metrics(self):
        prefs = {**default_preferences(), 'personnel': '11', 'formation': 'gun_trips', 'installed_call_ids': ['mesh', 'power', 'verticals']}
        fit = suggest_concepts({**DEFAULT_STATE, 'yardline_100': 5, 'ydstogo': 5}, prefs)
        self.assertEqual(fit['eligible_call_ids'], ['mesh'])
        exclusions = {item['call_id']: item['reasons'] for item in fit['excluded']}
        self.assertTrue(any('personnel' in reason for reason in exclusions['power']))
        self.assertTrue(any('goal line' in reason for reason in exclusions['verticals']))
        for item in fit['suggestions']:
            self.assertTrue(item['reasons'])
            self.assertFalse(set(item) & {'epa', 'expected_epa', 'probability', 'confidence'})
        empty = suggest_concepts(DEFAULT_STATE, {**prefs, 'installed_call_ids': []})
        self.assertEqual(empty['suggestions'], [])
        self.assertEqual(len(empty['excluded']), len(PLAYBOOK))

    def test_objective_and_action_filter(self):
        clock = suggest_concepts(DEFAULT_STATE, {**default_preferences(), 'objective': 'clock'})
        explosive = suggest_concepts(DEFAULT_STATE, {**default_preferences(), 'objective': 'explosive'})
        self.assertNotEqual(clock['suggestions'], explosive['suggestions'])
        run = suggest_concepts({**DEFAULT_STATE, 'action_filter': 'run'})
        types = {call['id']: call['type'] for call in PLAYBOOK}
        self.assertTrue(all(types[id] == 'RUN' for id in run['eligible_call_ids']))

    def test_bad_preferences_are_rejected(self):
        for update in [{'personnel': []}, {'objective': 'guaranteed_win'}, {'installed_call_ids': ['mesh', 'mesh']},
                       {'installed_call_ids': ['bogus']}, {'installed_call_ids': 'mesh'}, {'anticipated_coverage': 'bogus'}]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_preferences({**default_preferences(), **update}, COVERAGES)


class FitAPITests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db = Path(directory.name) / 'test.sqlite'
        self.app = create_app(Path(directory.name) / 'absent', db_path=self.db, data_dir=directory.name)
        self.client = self.app.test_client()
        self.session = self.client.post('/api/sessions', json={'state': DEFAULT_STATE}).get_json()
        self.url = '/api/sessions/' + self.session['id']

    def payload(self, **values):
        return dict(revision=self.session['revision'], mutation_id=uuid.uuid4().hex, **values)

    def mutate(self, suffix='', method='patch', **values):
        response = getattr(self.client, method)(self.url + suffix, json=self.payload(**values))
        self.assertEqual(response.status_code, 200, response.get_json())
        self.session = response.get_json()
        return self.session

    def test_preferences_persist_queue_survives_edit_and_ineligible_queue_rejected(self):
        self.mutate('/queue', 'post', call_id='mesh')
        prefs = {**default_preferences(), 'personnel': '21', 'formation': 'under_center'}
        self.mutate(state=DEFAULT_STATE, preferences=prefs)
        self.assertEqual(self.session['queue'][0]['call_id'], 'mesh')
        saved = self.client.get(self.url).get_json()
        self.assertEqual(saved['preferences']['personnel'], '21')
        blocked = self.client.post(self.url + '/queue', json=self.payload(call_id='mesh'))
        self.assertEqual(blocked.status_code, 400)
        self.mutate('/queue', 'post', call_id='power')

    def test_snapshot_preserves_pre_snap_inputs_and_undo(self):
        prefs = {**default_preferences(), 'anticipated_coverage': 'MAN', 'personnel': '11'}
        self.mutate(state=DEFAULT_STATE, preferences=prefs)
        fit = self.client.get(self.url + '/evaluation').get_json()['situational_fit']
        presentation = dict(revision=self.session['revision'], candidate_ids=[p['call_id'] for p in fit['suggestions']])
        self.mutate('/queue', 'post', call_id='mesh', presentation=presentation)
        queue = self.session['queue'][0]
        presentation['revision'] = self.session['revision']
        self.mutate('/plays', 'post', call_id='mesh', queue_id=queue['id'], presentation=presentation,
                    outcome=dict(kind='gain', yards=4, elapsed_seconds=10, observed_coverage='COVER_3'))
        entry = self.session['plays'][0]
        self.assertEqual(entry['decision_context']['preferences']['anticipated_coverage'], 'MAN')
        self.assertEqual(entry['outcome']['observed_coverage'], 'COVER_3')
        self.assertEqual(entry['decision_context']['displayed_candidate_ids'], presentation['candidate_ids'])
        self.assertEqual(entry['queued_decision_context'], queue['decision_context'])
        self.assertEqual(self.session['preferences']['anticipated_coverage'], 'UNKNOWN')
        self.mutate('/undo', 'post')
        self.assertEqual(self.session['preferences']['anticipated_coverage'], 'MAN')
        self.assertEqual(self.session['queue'][0], queue)

    def test_stale_presentation_is_atomic_and_actual_excluded_call_can_be_logged(self):
        response = self.client.post(self.url + '/plays', json=self.payload(call_id='mesh',
            presentation=dict(revision=99, candidate_ids=[]), outcome=dict(kind='gain', yards=2, elapsed_seconds=5)))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(self.url).get_json()['revision'], 0)
        self.mutate(state={**DEFAULT_STATE, 'action_filter': 'run'})
        self.mutate('/plays', 'post', call_id='mesh', outcome=dict(kind='gain', yards=2, elapsed_seconds=5))
        context = self.session['plays'][0]['decision_context']
        self.assertTrue(context['selected_call_exclusions'])
        self.assertIsNone(context['displayed_candidate_ids'])

    def test_legacy_session_gets_defaults_without_rewriting_history(self):
        with sqlite3.connect(self.db) as connection:
            body = json.loads(connection.execute('SELECT body FROM sessions WHERE id=?', (self.session['id'],)).fetchone()[0])
            del body['preferences']
            connection.execute('UPDATE sessions SET body=? WHERE id=?', (json.dumps(body), self.session['id']))
        saved = self.client.get(self.url).get_json()
        self.assertEqual(saved['preferences'], default_preferences())
        self.assertEqual(saved['revision'], 0)
        self.assertEqual(saved['plays'], [])
        self.assertTrue(self.client.get(self.url + '/evaluation').get_json()['situational_fit']['suggestions'])
        self.mutate('/plays', 'post', call_id='zone', outcome=dict(kind='gain', yards=2, elapsed_seconds=5))

    def test_preferences_do_not_enter_model_features(self):
        bundle = {'schema_version': 1, 'teams': ['KC', 'BUF'], 'model_id': 'fixture'}
        client = create_app(bundle=bundle, db_path=self.db, data_dir=self.db.parent).test_client()
        with patch('backend.decision_support.dashboard.compare_options', return_value={'options': []}) as compare:
            client.get(self.url + '/evaluation')
            before = compare.call_args_list[0]
            self.mutate(state=DEFAULT_STATE, preferences={**default_preferences(), 'objective': 'clock', 'anticipated_coverage': 'MAN'})
            compare.reset_mock()
            client.get(self.url + '/evaluation')
            self.assertEqual(before, compare.call_args_list[0])


if __name__ == '__main__':
    unittest.main()
