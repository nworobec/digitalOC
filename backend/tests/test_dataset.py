import copy
import tempfile
import unittest
from pathlib import Path

from backend.decision_support.api import create_app
from backend.decision_support.data import FEATURES
from backend.decision_support.dataset import build_dataset
from backend.decision_support.game import DEFAULT_STATE
from backend.decision_support.playbook import default_preferences


def session(index=1, concept='mesh', play_id='1', game=None, day=None):
    game = game or f'GAME-{index}'
    day = day or f'2024-09-{index:02}'
    before = dict(DEFAULT_STATE)
    review = dict(status='approved', reviewer='Fixture', source_type='real_game', source_reference='Test fixture only',
                  game_id=game, source_play_id=play_id, game_date=day, actual_call_id=concept, actual_personnel='11',
                  actual_formation='gun_doubles', observed_coverage='MAN', actual_kind='gain', actual_yards=4,
                  penalty_status='none', outcome_verified=True, before_state_verified=True, notes='', review_number=1)
    play = dict(id=f'local-{index}-{concept}-{play_id}', call_id=concept, before=before,
                outcome=dict(kind='gain', yards=4, elapsed_seconds=10),
                after={**before, 'yardline_100': 71}, reviews=[review],
                decision_context=dict(situation=copy.deepcopy(before), preferences=default_preferences(),
                                      catalog_version='starter-2', suggestions=[dict(expected_epa=999)], outcome_model_id='fixture'))
    return dict(id=f'session-{index}', revision=2, plays=[play])


class DatasetTests(unittest.TestCase):
    def test_empty_and_small_data_are_explicitly_blocked(self):
        empty = build_dataset([])
        self.assertEqual(empty['status'], 'blocked')
        self.assertEqual(empty['summary']['included_plays'], 0)
        small = build_dataset([session()])
        self.assertEqual(small['rows'][0]['split'], 'unassigned')
        self.assertEqual(small['status'], 'blocked')

    def test_features_are_allowlisted_and_targets_never_predicted(self):
        result = build_dataset([session()])
        row = result['rows'][0]
        self.assertEqual(set(row['features']), set(FEATURES))
        self.assertEqual(row['targets'], {'yards_gained': 4})
        self.assertEqual(row['action'], {'concept_id': 'mesh', 'type': 'pass'})
        self.assertFalse(set(row['features']) & {'observed_coverage', 'actual_formation', 'actual_personnel', 'after', 'expected_epa', 'yards_gained'})

    def test_duplicate_aliases_quarantine_all_until_explicit_exclusion(self):
        first, second = session(1), session(2, game=' game-1 ', day='2024-09-01')
        result = build_dataset([first, second])
        self.assertEqual(result['summary']['included_plays'], 0)
        self.assertEqual(result['summary']['duplicate_source_groups'], 1)
        second['plays'][0]['reviews'][0].update(status='excluded', notes='Duplicate copy; keep first session')
        result = build_dataset([first, second])
        self.assertEqual(result['summary']['included_plays'], 1)

    def test_conflicting_game_dates_or_teams_never_cross_splits(self):
        first, second = session(1), session(2, game='GAME-1', play_id='2')
        result = build_dataset([first, second])
        self.assertEqual(result['summary']['included_plays'], 0)
        self.assertEqual(result['conflicting_game_ids'], ['GAME-1'])
        second['plays'][0]['reviews'][0]['game_date'] = '2024-09-01'
        second['plays'][0]['before']['defteam'] = 'BAL'
        second['plays'][0]['decision_context']['situation']['defteam'] = 'BAL'
        self.assertEqual(build_dataset([first, second])['summary']['included_plays'], 0)

    def test_old_missing_ids_test_sources_and_false_approval_are_blocked(self):
        for updates in [dict(source_play_id=''), dict(source_type='test'), dict(outcome_verified=False),
                        dict(game_date='20240901'), dict(actual_call_id='invented')]:
            with self.subTest(updates=updates):
                record = session()
                record['plays'][0]['reviews'][0].update(updates)
                self.assertEqual(build_dataset([record])['summary']['included_plays'], 0)

    def test_outcome_correction_quarantines_later_session_states(self):
        record = session()
        later = copy.deepcopy(session(play_id='2')['plays'][0])
        record['plays'].append(later)
        record['plays'][0]['reviews'][0].update(actual_yards=5, notes='Corrected yards')
        result = build_dataset([record])
        self.assertEqual(result['summary']['included_plays'], 0)
        self.assertTrue(all('unreconciled_outcome_or_penalty_in_session_history' in item['blockers'] for item in result['exclusions']))

    def test_mismatched_decision_snapshot_is_excluded(self):
        record = session()
        record['plays'][0]['decision_context']['situation']['down'] = 4
        self.assertEqual(build_dataset([record])['summary']['included_plays'], 0)

    def test_date_groups_determinism_and_frozen_cutoffs(self):
        records = [session(index) for index in range(1, 11)]
        result = build_dataset(records)
        self.assertEqual(result['summary']['splits'], {'train': 6, 'validation': 2, 'test': 2})
        self.assertEqual(result['sha256'], build_dataset(list(reversed(records)))['sha256'])
        fixed = build_dataset(records, '2024-09-04', '2024-09-07')
        self.assertEqual(fixed['summary']['splits'], {'train': 4, 'validation': 3, 'test': 3})
        self.assertNotEqual(result['dataset_id'], fixed['dataset_id'])
        for args in [('2024-09-01', None), ('2024-09-05', '2024-09-01')]:
            with self.assertRaises(ValueError):
                build_dataset(records, *args)

    def test_support_gates_need_multiple_concepts_and_games_in_every_split(self):
        records = []
        for index in range(1, 11):
            game = session(index)
            game['plays'] = [session(index, concept, f'{concept}-{play_id}')['plays'][0]
                             for concept in ('mesh', 'zone') for play_id in range(20)]
            records.append(game)
        result = build_dataset(records)
        self.assertEqual(result['status'], 'eligible_for_experimental_training')
        self.assertEqual(sum(item['meets_planning_gate'] for item in result['concept_support']), 2)
        mapping = {}
        for row in result['rows']:
            mapping.setdefault(row['source_game_id'], set()).add(row['split'])
        self.assertTrue(all(len(values) == 1 for values in mapping.values()))

    def test_endpoint_preview_download_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = create_app(root / 'absent', db_path=root / 'db.sqlite', data_dir=root).test_client()
            response = client.get('/api/data/dataset')
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('rows', response.get_json())
            download = client.get('/api/data/dataset?download=1')
            self.assertIn('attachment;', download.headers['Content-Disposition'])
            self.assertEqual(download.get_json()['rows'], [])
            self.assertEqual(download.get_json()['sha256'], response.get_json()['sha256'])
            self.assertEqual(client.get('/api/data/dataset?train_through=2024-09-01').status_code, 400)
