import csv
import tempfile
import unittest
from pathlib import Path

from backend.decision_support.api import create_app
from backend.decision_support.labeling import FIELDS, PART_FIELDS, source_season


def raw(play_id, **updates):
    return dict(game_id='2024_01_KC_BUF', play_id=play_id, game_date='9/8/2024', desc='Source description',
                posteam='KC', defteam='BUF', down=1, ydstogo=10, yardline_100=75, qtr=1, quarter_seconds_remaining=900,
                game_seconds_remaining=3600, score_differential=0, posteam_timeouts_remaining=3, defteam_timeouts_remaining=3,
                posteam_score=0, defteam_score=0, play_type='pass', yards_gained=4, epa=.2, penalty=0,
                qb_kneel=0, qb_spike=0, qb_scramble=0, qb_dropback=1, sack=0, interception=0,
                fumble_lost=0, touchdown=0, safety=0, incomplete_pass=0, drive=1) | updates


def write(path, fields, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


class LabelingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.source = self.root / 'pbp_2024_0.csv'
        write(self.source, FIELDS, [raw(1), raw(2, play_type='run', qb_dropback=0), raw(3, penalty=1)])
        write(self.root / 'pbp_2024_1.csv', FIELDS, [])
        write(self.root / 'pbp_participation_2024.csv', PART_FIELDS, [dict(nflverse_game_id='2024_01_KC_BUF', play_id=1, route='SCREEN', offense_formation='SHOTGUN', offense_personnel='1 RB, 1 TE, 3 WR', defense_coverage_type='COVER_3')])
        self.client = create_app(self.root / 'absent', db_path=self.root / 'db.sqlite', data_dir=self.root).test_client()

    def stage(self, ids=['1']):
        return self.client.post('/api/labeling/import', json=dict(game_id='2024_01_KC_BUF', play_ids=ids))

    def test_browse_actual_evidence_without_invented_concepts(self):
        games = self.client.get('/api/labeling/games?season=2024').get_json()['games']
        self.assertEqual(games[0]['plays'], 2)
        response = self.client.get('/api/labeling/plays?season=2024&game_id=2024_01_KC_BUF&action=pass').get_json()
        self.assertEqual(response['total'], 1)
        record = response['plays'][0]
        self.assertEqual(record['source']['raw_labels']['route'], 'SCREEN')
        self.assertNotIn('concept_id', record)
        self.assertEqual(record['game_date'], '2024-09-08')
        self.assertIsNone(record['outcome']['elapsed_seconds'])

    def test_staging_idempotent_review_only_and_no_fake_predictions(self):
        first = self.stage(['1', '2']).get_json()
        second = self.stage(['2', '1']).get_json()
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'review_only')
        self.assertEqual(first['plays'][0]['call_id'], 'unlabeled')
        self.assertEqual(first['plays'][0]['reviews'], [])
        self.assertIsNone(first['plays'][0]['after'])
        self.assertEqual(first['plays'][0]['decision_context']['suggestions'], [])
        result = self.client.get('/api/data/dataset').get_json()
        self.assertEqual(result['summary']['included_plays'], 0)
        self.assertEqual(result['summary']['excluded_plays'], 2)
        response = self.client.post('/api/sessions/' + first['id'] + '/drive', json=dict(revision=first['revision'], mutation_id='test-drive-change', state=first['state']))
        self.assertEqual(response.status_code, 400)

    def test_new_records_merge_without_overwriting_prior_reviews(self):
        first = self.stage().get_json()
        url = '/api/sessions/' + first['id']
        review = dict(status='draft', reviewer='Coach', source_type='real_game', source_reference='', game_id='2024_01_KC_BUF',
                      source_play_id='1', game_date='2024-09-08', actual_call_id='unknown', actual_personnel='unknown',
                      actual_formation='unknown', observed_coverage='UNKNOWN', actual_kind='gain', actual_yards=4,
                      penalty_status='none', outcome_verified=False, before_state_verified=False, notes='Need film')
        response = self.client.post(url + '/plays/source-1/review', json=dict(revision=first['revision'], mutation_id='test-draft-review', review=review))
        self.assertEqual(response.status_code, 200, response.get_json())
        merged = self.stage(['1', '2']).get_json()
        self.assertEqual(len(merged['plays']), 2)
        self.assertEqual(merged['plays'][0]['reviews'][0]['notes'], 'Need film')
        self.assertEqual(self.client.get(url + '/export').get_json()['records'][0]['original']['historical_source']['play_id'], '1')

    def test_invalid_selection_is_atomic_and_changed_sources_conflict(self):
        self.assertEqual(self.stage(['1', '3']).status_code, 400)
        self.assertEqual(self.client.get('/api/sessions').get_json()['sessions'], [])
        self.stage()
        write(self.source, FIELDS, [raw(1, yards_gained=5), raw(2)])
        self.assertEqual(self.stage().status_code, 409)

    def test_duplicate_keys_fail_instead_of_multiplying_records(self):
        write(self.source, FIELDS, [raw(1), raw(1)])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            source_season(self.root, 2024)

    def test_query_validation(self):
        for path in ['/api/labeling/games?season=bad', '/api/labeling/games?season=2025',
                     '/api/labeling/plays?season=2024&game_id=2024_01_KC_BUF&page=-1']:
            self.assertEqual(self.client.get(path).status_code, 400)
        self.assertEqual(self.client.get('/api/labeling/plays?game_id=nope').status_code, 404)
        self.assertEqual(self.stage([]).status_code, 400)
