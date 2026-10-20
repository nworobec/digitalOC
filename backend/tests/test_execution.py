import copy
import unittest
from backend.tests.test_dataset import session
from backend.decision_support.execution import empty_execution
from backend.decision_support.review import validate_review
from backend.decision_support.dataset import build_dataset, REVIEW_FIELDS


class ExecutionTests(unittest.TestCase):
    def fixture(self):
        record = session()
        play = record['plays'][0]
        execution = empty_execution()
        execution.update(relationship='no_plan', strength='right', motion='No motion', motion_verified=True, assignments_verified=True)
        for item in execution['assignments']:
            item.update(route='N/A', blocking='Reviewed assignment')
        play['reviews'][0]['execution'] = execution
        return record, play, execution

    def test_verified_labels_export_separately_and_do_not_leak_into_features(self):
        record, play, execution = self.fixture()
        original = copy.deepcopy(play['decision_context'])
        report = build_dataset([record])
        self.assertEqual(report['design_readiness']['verified_eligible_plays'], 1)
        self.assertEqual(report['design_readiness']['status'], 'blocked')
        self.assertEqual(report['rows'][0]['design_review']['executed'], execution)
        self.assertNotIn('execution', report['rows'][0]['features'])
        self.assertEqual(play['decision_context'], original)
        self.assertEqual(report['config']['schema_version'], 'concept-dataset-3')

    def test_unverified_labels_and_duplicate_plays_do_not_count(self):
        record, play, execution = self.fixture()
        execution['assignments_verified'] = False
        report = build_dataset([record])
        self.assertEqual(report['design_readiness']['verified_eligible_plays'], 0)
        self.assertIn('Executed assignments have not been verified', report['design_readiness']['missing_labels'])
        execution['assignments_verified'] = True
        duplicate = copy.deepcopy(record)
        duplicate['id'] = 'copy'
        self.assertEqual(build_dataset([record, duplicate])['design_readiness']['verified_eligible_plays'], 0)

    def test_invalid_verification_and_false_as_planned_rejected(self):
        for field, value in [('motion', ''), ('assignments', []), ('relationship', 'as_planned')]:
            record, play, execution = self.fixture()
            execution[field] = value
            report = build_dataset([record])
            self.assertEqual(report['summary']['included_plays'], 0)
        record, play, execution = self.fixture()
        definition = {key: execution[key] for key in ['strength', 'motion', 'assignments']}
        definition.update(personnel='11', formation='gun_doubles')
        play['decision_context']['play_design'] = dict(version=2, definition=copy.deepcopy(definition))
        execution['relationship'] = 'as_planned'
        self.assertEqual(build_dataset([record])['design_readiness']['verified_eligible_plays'], 1)
        execution['assignments'][0]['route'] = 'Changed route'
        self.assertEqual(build_dataset([record])['summary']['included_plays'], 0)
        execution['relationship'] = 'modified'
        play['reviews'][0]['notes'] = 'Film shows a route adjustment'
        self.assertEqual(build_dataset([record])['design_readiness']['verified_eligible_plays'], 1)

    def test_legacy_review_still_valid_but_missing_execution_labels(self):
        report = build_dataset([session()])
        self.assertEqual(report['summary']['included_plays'], 1)
        self.assertEqual(report['design_readiness']['verified_eligible_plays'], 0)
