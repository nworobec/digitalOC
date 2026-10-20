import copy
import tempfile
import unittest
import uuid
from pathlib import Path
from backend.decision_support.api import create_app
from backend.decision_support.game import DEFAULT_STATE
from backend.decision_support.designs import default_design
from backend.decision_support.layouts import DEFAULT_POSITIONS


class DesignTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        self.client = create_app(root / 'missing', db_path=root / 'db', data_dir=root).test_client()
        self.session = self.client.post('/api/sessions', json={'state': DEFAULT_STATE}).get_json()
        self.url = '/api/sessions/' + self.session['id']
        self.design = default_design()
        self.design.update(personnel='11', formation='gun_trips', motion='Slot short motion')
        self.design['assignments'][0]['route'] = 'Shallow cross'

    def payload(self, **values):
        return dict(revision=self.session['revision'], mutation_id=uuid.uuid4().hex, **values)

    def save(self, **values):
        response = self.client.put(self.url + '/layouts/mesh', json=self.payload(positions=DEFAULT_POSITIONS, **values))
        self.assertEqual(response.status_code, 200, response.get_json())
        self.session = response.get_json()

    def test_confirmed_design_refreshes_rules_but_preserves_model_inputs(self):
        before = self.client.get(self.url + '/evaluation').get_json()
        self.save(design=self.design)
        after = self.client.get(self.url + '/evaluation').get_json()
        self.assertEqual(self.session['preferences']['formation'], 'gun_trips')
        self.assertEqual(self.session['preferences']['personnel'], '11')
        self.assertNotIn('power', after['situational_fit']['eligible_call_ids'])
        self.assertEqual(after['outcome_input_snapshot'], before['outcome_input_snapshot'])
        self.assertEqual(after['design_versions'], {'mesh': 1})
        self.assertFalse(after['design_outcomes'])
        self.assertEqual(self.client.get(self.url).get_json()['designs']['mesh']['definition'], self.design)
        self.save(design=self.design)
        self.assertEqual(self.session['designs']['mesh']['version'], 1)

    def test_visual_edits_leave_design_and_plan_context_unchanged(self):
        self.save(design=self.design)
        self.session = self.client.post(self.url + '/plan/generate', json=self.payload()).get_json()
        plan = self.session['coaching_plan']
        positions = copy.deepcopy(DEFAULT_POSITIONS)
        positions[0] = [95, 215]
        self.session = self.client.put(self.url + '/layouts/mesh', json=self.payload(positions=positions)).get_json()
        self.assertEqual(self.session['designs']['mesh']['version'], 1)
        response = self.client.put(self.url + '/plan', json=self.payload(context_id=plan['context_id'], content=plan['content']))
        self.assertEqual(response.status_code, 200)
        self.session = response.get_json()
        self.design['motion'] = 'No motion'
        self.save(design=self.design)
        self.assertEqual(self.session['designs']['mesh']['version'], 2)
        response = self.client.put(self.url + '/plan', json=self.payload(context_id=plan['context_id'], content=plan['content']))
        self.assertEqual(response.status_code, 409)

    def test_queue_keeps_original_design_when_execution_design_changes(self):
        self.save(design=self.design)
        self.session = self.client.post(self.url + '/queue', json=self.payload(call_id='mesh')).get_json()
        entry = self.session['queue'][0]
        self.design['assignments'][0]['route'] = 'Adjusted cross'
        self.save(design=self.design)
        self.session = self.client.post(self.url + '/plays', json=self.payload(call_id='mesh', queue_id=entry['id'], outcome=dict(kind='gain', yards=3, elapsed_seconds=10))).get_json()
        play = self.session['plays'][0]
        self.assertEqual(play['queued_decision_context']['play_design']['version'], 1)
        self.assertEqual(play['decision_context']['play_design']['version'], 2)
        self.assertEqual(entry['decision_context']['play_design']['definition']['assignments'][0]['route'], 'Shallow cross')

    def test_invalid_and_conflicting_edits_are_atomic(self):
        for key, value in [('personnel', '21'), ('formation', 'under_center'), ('assignments', []), ('motion', 'x' * 501)]:
            design = {**self.design, key: value}
            response = self.client.put(self.url + '/layouts/mesh', json=self.payload(positions=DEFAULT_POSITIONS, design=design))
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(self.url).get_json()['revision'], 0)
        payload = self.payload(positions=DEFAULT_POSITIONS, design=self.design)
        first = self.client.put(self.url + '/layouts/mesh', json=payload)
        self.assertEqual(first.get_json(), self.client.put(self.url + '/layouts/mesh', json=payload).get_json())
        self.assertEqual(self.client.put(self.url + '/layouts/mesh', json=self.payload(positions=DEFAULT_POSITIONS, design=self.design)).status_code, 409)
