import copy
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from backend.decision_support.api import create_app
from backend.decision_support.game import DEFAULT_STATE
from backend.decision_support.plans import draft_plan
from backend.decision_support.playbook import default_preferences


class PlanTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.client = create_app(self.root / 'missing', db_path=self.root / 'db', data_dir=self.root).test_client()
        self.session = self.client.post('/api/sessions', json={'state': DEFAULT_STATE}).get_json()
        self.url = '/api/sessions/' + self.session['id']

    def payload(self, **kw):
        return dict(revision=self.session['revision'], mutation_id=uuid.uuid4().hex, **kw)

    def generate(self):
        response = self.client.post(self.url + '/plan/generate', json=self.payload())
        self.assertEqual(response.status_code, 200, response.get_json())
        self.session = response.get_json()
        return self.session['coaching_plan']

    def test_persistence_edit_and_no_game_side_effects(self):
        plan = self.generate()
        self.assertEqual(plan['evidence']['status'], 'unavailable')
        plan['content']['notes'] = 'Coach: protect the right tackle.'
        payload = self.payload(context_id=plan['context_id'], content=plan['content'])
        response = self.client.put(self.url + '/plan', json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), self.client.put(self.url + '/plan', json=payload).get_json())
        resumed = self.client.get(self.url).get_json()
        self.assertEqual(resumed['coaching_plan']['content']['notes'], plan['content']['notes'])
        self.assertTrue(resumed['coaching_plan']['edited_by_coach'])
        self.assertEqual(resumed['state'], DEFAULT_STATE)
        self.assertEqual(resumed['queue'], [])
        self.assertEqual(resumed['plays'], [])
        other = self.client.post('/api/sessions', json={'state': DEFAULT_STATE}).get_json()
        self.assertNotIn('coaching_plan', other)

    def test_constraints_empty_playbook_and_fabricated_calls(self):
        prefs = default_preferences()
        prefs['installed_call_ids'] = []
        session = dict(state=DEFAULT_STATE, preferences=prefs)
        content = draft_plan(session, {'status': 'unavailable'})
        self.assertEqual(content['opening_script'], [])
        self.assertEqual(content['counters'], [])
        plan = self.generate()
        for bad in ['invented', None, {}, []]:
            content = copy.deepcopy(plan['content'])
            content['opening_script'][0]['call_id'] = bad
            response = self.client.put(self.url + '/plan', json=self.payload(context_id=plan['context_id'], content=content))
            self.assertEqual(response.status_code, 400)
        content = copy.deepcopy(plan['content'])
        content['notes'] = 'x' * 6001
        self.assertEqual(self.client.put(self.url + '/plan', json=self.payload(context_id=plan['context_id'], content=content)).status_code, 400)

    def test_stale_context_and_revision_preserve_plan(self):
        plan = self.generate()
        old = self.payload(context_id=plan['context_id'], content=plan['content'])
        state = {**DEFAULT_STATE, 'ydstogo': 15}
        self.session = self.client.patch(self.url, json=self.payload(state=state)).get_json()
        self.assertEqual(self.client.put(self.url + '/plan', json=old).status_code, 409)
        self.assertEqual(self.client.put(self.url + '/plan', json=self.payload(context_id=plan['context_id'], content=plan['content'])).status_code, 409)
        self.assertEqual(self.client.get(self.url).get_json()['coaching_plan'], plan)
        self.assertNotEqual(self.generate()['context_id'], plan['context_id'])

    def test_opponent_evidence_informs_conditional_counters(self):
        evidence = dict(status='historical_frequencies', distribution=[dict(coverage='COVER_3', count=80, frequency=.8)], sample_count=100, seasons=[2024], scope='opponent and down', source='fixture')
        with patch('backend.decision_support.plans.describe_defense', return_value=evidence):
            plan = self.generate()
        self.assertEqual(plan['evidence'], evidence)
        self.assertIn('COVER 3', plan['content']['counters'][0]['condition'])
        self.assertTrue(plan['content']['counters'][0]['condition'].startswith('If'))
