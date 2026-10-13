import copy
import tempfile
import unittest
import uuid
from pathlib import Path
from backend.decision_support.api import create_app
from backend.decision_support.game import DEFAULT_STATE
from backend.decision_support.layouts import DEFAULT_POSITIONS


class LayoutTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.db = self.root / 'test.sqlite'
        self.client = create_app(self.root / 'absent', db_path=self.db, data_dir=self.root).test_client()
        self.session = self.client.post('/api/sessions', json={'state': DEFAULT_STATE}).get_json()
        self.url = '/api/sessions/' + self.session['id']

    def payload(self, **values):
        return dict(revision=self.session['revision'], mutation_id=uuid.uuid4().hex, **values)

    def save(self, positions):
        response = self.client.put(self.url + '/layouts/mesh', json=self.payload(positions=positions))
        self.assertEqual(response.status_code, 200, response.get_json())
        self.session = response.get_json()

    def test_save_resume_reset_and_session_isolation(self):
        positions = copy.deepcopy(DEFAULT_POSITIONS)
        positions[0] = [90, 215]
        self.save(positions)
        client = create_app(self.root / 'absent', db_path=self.db, data_dir=self.root).test_client()
        self.assertEqual(client.get(self.url).get_json()['layouts']['mesh']['positions'], positions)
        other = self.client.post('/api/sessions', json={'state': DEFAULT_STATE}).get_json()
        self.assertNotIn('mesh', other.get('layouts', {}))
        self.save(None)
        self.assertNotIn('mesh', self.session['layouts'])
        self.assertEqual(self.session['state'], DEFAULT_STATE)
        self.assertEqual(self.session['plays'], [])

    def test_invalid_positions_cannot_modify_saved_state(self):
        invalid = [[], [[0, 202]] + DEFAULT_POSITIONS[1:], [[76, 199]] + DEFAULT_POSITIONS[1:],
                   [[True, 202]] + DEFAULT_POSITIONS[1:], [[float('nan'), 202]] + DEFAULT_POSITIONS[1:],
                   [DEFAULT_POSITIONS[1]] + DEFAULT_POSITIONS[1:]]
        for positions in invalid:
            with self.subTest(positions=positions):
                response = self.client.put(self.url + '/layouts/mesh', json=self.payload(positions=positions))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.client.get(self.url).get_json()['revision'], 0)
        self.assertEqual(self.client.put(self.url + '/layouts/unknown', json=self.payload(positions=DEFAULT_POSITIONS)).status_code, 400)

    def test_retry_conflict_and_immutable_queue_snapshot(self):
        positions = copy.deepcopy(DEFAULT_POSITIONS)
        positions[0] = [90, 210]
        payload = self.payload(positions=positions)
        first = self.client.put(self.url + '/layouts/mesh', json=payload).get_json()
        self.assertEqual(first, self.client.put(self.url + '/layouts/mesh', json=payload).get_json())
        self.assertEqual(self.client.put(self.url + '/layouts/mesh', json=self.payload(positions=None)).status_code, 409)
        self.session = first
        self.session = self.client.post(self.url + '/queue', json=self.payload(call_id='mesh')).get_json()
        queued = copy.deepcopy(self.session['queue'][0])
        positions[0] = [110, 215]
        self.save(positions)
        self.assertEqual(self.session['queue'][0], queued)
        self.session = self.client.post(self.url + '/plays', json=self.payload(call_id='mesh', queue_id=queued['id'], outcome=dict(kind='gain', yards=4, elapsed_seconds=10))).get_json()
        play = self.session['plays'][0]
        self.assertEqual(play['decision_context']['diagram_layout']['positions'][0], [110, 215])
        self.assertEqual(play['queued_decision_context']['diagram_layout']['positions'][0], [90, 210])
        self.save(None)
        self.assertEqual(self.session['plays'][0], play)
        exported = self.client.get(self.url + '/export').get_json()
        self.assertEqual(exported['records'][0]['original']['decision_context']['diagram_layout']['positions'][0], [110, 215])

    def test_alignment_does_not_affect_rules(self):
        before = self.client.get(self.url + '/evaluation').get_json()['situational_fit']
        positions = copy.deepcopy(DEFAULT_POSITIONS)
        positions[0] = [90, 215]
        self.save(positions)
        after = self.client.get(self.url + '/evaluation').get_json()['situational_fit']
        self.assertEqual(before, after)
