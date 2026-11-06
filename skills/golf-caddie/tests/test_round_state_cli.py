import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'round_state_cli.py'


class CliTests(unittest.TestCase):
    def run_cli(self, db, owner, requests):
        p = subprocess.run([sys.executable, '-B', str(SCRIPT), '--database', str(db), '--owner', owner],
                           input='\n'.join(json.dumps(r, ensure_ascii=False) for r in requests),
                           capture_output=True, text=True, check=True)
        return [json.loads(line) for line in p.stdout.splitlines()]

    def test_persisted_confirmed_score_replays_in_second_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'state.sqlite'
            requests = [dict(action='create', round_id='r'),
                dict(round_id='r', command_id='e', kind='evidence', payload=dict(id='u', revision=1, phase='final', source='user', observed_at='2026-11-06T00:00:00Z', text='一号洞五杆')),
                dict(round_id='r', command_id='p', kind='propose', payload=dict(id='p', base_version=1, evidence_ids=['u:1'], operations=[dict(path='holes.1.total', value=5, status='confirmed')])),
                dict(round_id='r', command_id='c', kind='confirm', payload=dict(id='p', confirmation_version=2, explicit=True))]
            self.assertTrue(all(r['ok'] for r in self.run_cli(db, 'alice', requests)))
            read = self.run_cli(db, 'alice', [dict(action=a, round_id='r') for a in ('state', 'replay')])
            self.assertEqual(read[0], read[1])
            self.assertEqual(read[0]['result']['facts']['holes.1.total']['value'], 5)
            self.assertFalse(self.run_cli(db, 'bob', [dict(action='state', round_id='r')])[0]['ok'])

    def test_error_line_does_not_kill_following_requests(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = self.run_cli(Path(tmp) / 'state.sqlite', 'alice',
                                  [dict(action='unsupported', round_id='r'), dict(action='create', round_id='r')])
            self.assertFalse(results[0]['ok'])
            self.assertTrue(results[1]['ok'])
