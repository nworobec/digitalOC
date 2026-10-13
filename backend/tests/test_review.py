import copy
import csv
import io
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from backend.decision_support.api import create_app
from backend.decision_support.audit import audit_sources
from backend.decision_support.game import DEFAULT_STATE


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.client = create_app(root / 'absent', db_path=root / 'test.sqlite', data_dir=root).test_client()
        self.session = self.client.post('/api/sessions', json={'state': DEFAULT_STATE}).get_json()
        self.url = '/api/sessions/' + self.session['id']
        self.session = self.client.post(self.url + '/plays', json=self.payload(call_id='mesh', outcome=dict(kind='gain', yards=4, elapsed_seconds=10))).get_json()
        self.play = copy.deepcopy(self.session['plays'][0])
        self.review_url = self.url + '/plays/' + self.play['id'] + '/review'
        self.review = dict(status='approved', reviewer='Coach', source_type='real_game', source_reference='Film 00:15',
                           game_id='2024_01_KC_BUF', game_date='2024-09-08', actual_call_id='mesh', actual_personnel='11',
                           actual_formation='gun_trips', observed_coverage='COVER_3', actual_kind='gain', actual_yards=4,
                           penalty_status='none', outcome_verified=True, before_state_verified=True, notes='Checked against film')

    def payload(self, **values):
        return dict(revision=self.session['revision'], mutation_id=uuid.uuid4().hex, **values)

    def save(self, **updates):
        result = self.client.post(self.review_url, json=self.payload(review={**self.review, **updates}))
        self.assertEqual(result.status_code, 200, result.get_json())
        self.session = result.get_json()

    def row(self):
        return self.client.get(self.url + '/review').get_json()['records'][0]

    def test_approval_retains_original_and_exports_context(self):
        before = copy.deepcopy(self.session['state'])
        self.save()
        self.assertEqual(self.session['state'], before)
        self.assertFalse(self.session['can_undo'])
        record = self.row()
        self.assertTrue(record['readiness']['yardage_candidate'])
        self.assertTrue(record['readiness']['defensive_label_candidate'])
        self.assertFalse(record['readiness']['epa_candidate'])
        original = {k: v for k, v in record['original'].items() if k != 'reviews'}
        self.assertEqual(original, self.play)
        exported = self.client.get(self.url + '/export').get_json()
        self.assertEqual(exported['records'][0]['original']['decision_context'], self.play['decision_context'])
        self.assertEqual(exported['schema_version'], 1)

    def test_review_history_is_append_only_and_latest_controls_readiness(self):
        self.save()
        self.save(status='excluded', notes='Bad source alignment')
        row = self.row()
        self.assertEqual([r['status'] for r in row['original']['reviews']], ['approved', 'excluded'])
        self.assertFalse(row['readiness']['yardage_candidate'])
        self.assertEqual(row['latest_review']['review_number'], 2)

    def test_invalid_approvals_are_atomic(self):
        for update in [dict(outcome_verified=False), dict(before_state_verified=False), dict(actual_call_id='unknown'), dict(reviewer=''),
                       dict(source_reference=''), dict(game_date='not-date'), dict(actual_yards=1.2),
                       dict(actual_personnel='any'), dict(actual_call_id='zone', actual_kind='sack'),
                       dict(status='excluded', notes=''), dict(actual_yards=5, notes='')]:
            with self.subTest(update=update):
                result = self.client.post(self.review_url, json=self.payload(review={**self.review, **update}))
                self.assertEqual(result.status_code, 400)
                self.assertEqual(self.client.get(self.url).get_json()['revision'], self.session['revision'])
        self.assertEqual(self.row()['original'].get('reviews', []), [])

    def test_retry_and_stale_revision(self):
        payload = self.payload(review=self.review)
        first = self.client.post(self.review_url, json=payload)
        second = self.client.post(self.review_url, json=payload)
        self.assertEqual(first.get_json(), second.get_json())
        self.assertEqual(len(second.get_json()['plays'][0]['reviews']), 1)
        stale = self.client.post(self.review_url, json=self.payload(review=self.review))
        self.assertEqual(stale.status_code, 409)

    def test_test_data_penalties_and_corrections_remain_blocked(self):
        for update in [dict(source_type='test'), dict(source_type='practice'), dict(penalty_status='accepted'),
                       dict(actual_yards=5, notes='Film shows five; downstream state not reconciled')]:
            self.save(**update)
            self.assertFalse(self.row()['readiness']['yardage_candidate'])
        self.assertEqual(self.session['plays'][0]['outcome']['yards'], 4)
        self.assertEqual(self.session['state']['yardline_100'], 71)

    def test_unknown_coverage_only_blocks_defensive_target(self):
        self.save(observed_coverage='UNKNOWN')
        row = self.row()['readiness']
        self.assertTrue(row['yardage_candidate'])
        self.assertFalse(row['defensive_label_candidate'])

    def test_csv_escaping_formula_protection_and_empty_export(self):
        notes = '=HYPERLINK("bad")\nsecond, line'
        self.save(notes=notes)
        response = self.client.get(self.url + '/export?format=csv')
        row = next(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
        self.assertEqual(row['notes'], "'" + notes)
        self.assertEqual(json.loads(row['review_history_json'])[0]['notes'], notes)
        self.assertIn('attachment;', response.headers['Content-Disposition'])
        self.assertEqual(self.client.get(self.url + '/export?format=zip').status_code, 400)
        empty = self.client.post('/api/sessions', json={'state': DEFAULT_STATE}).get_json()
        rows = list(csv.DictReader(io.StringIO(self.client.get('/api/sessions/' + empty['id'] + '/export?format=csv').get_data(as_text=True))))
        self.assertEqual(rows, [])

    def test_unreviewed_export_and_audit_do_not_approve(self):
        self.assertFalse(self.row()['readiness']['yardage_candidate'])
        result = self.client.get('/api/data/audit').get_json()
        self.assertEqual(result['recorded']['statuses'], {'unreviewed': 1})
        self.assertEqual(result['historical']['status'], 'incomplete')
        self.assertEqual(self.client.get(self.url).get_json()['revision'], self.session['revision'])


class AuditTests(unittest.TestCase):
    def test_duplicates_missing_targets_and_route_not_concept(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'pbp_2024_0.csv').write_text('game_id,play_id,play_type,epa,yards_gained\ng1,1,pass,1.0,4\ng1,1,pass,inf,4\ng2,2,run,,3\ng3,,run,1,2\n')
            (root / 'pbp_participation_2024.csv').write_text('nflverse_game_id,play_id,route,offense_formation,defense_coverage_type\ng1,1,SCREEN,SHOTGUN,COVER_3\ng4,2,,,UNKNOWN\n')
            (root / 'merged_pass_model_data_2024.csv').write_text('concept\nmesh\n')
            audit = audit_sources(root)
            self.assertEqual(audit['keys']['pbp']['duplicate_extra_rows'], 1)
            self.assertEqual(audit['join']['matched_unique_keys'], 1)
            self.assertEqual(audit['summary']['recognized_concept_label_cells'], 0)
            self.assertEqual(audit['summary']['scrimmage_with_both_targets'], 2)
            participation = next(f for f in audit['files'] if f['scope'] == 'participation')
            self.assertEqual(participation['populated']['route'], 1)
            self.assertEqual(participation['populated']['defense_coverage_type'], 1)
            (root / 'pbp_2024_1.csv').write_text('game_id,play_id,play_type,epa,yards_gained\ng5,5,run,0.2,6\n')
            self.assertEqual(audit_sources(root)['summary']['pbp_rows'], 5)


if __name__ == '__main__':
    unittest.main()
