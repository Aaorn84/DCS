import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_scenario_runs_and_audits_corrected_execution(self):
        p=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/shot_chain_cli.py'),
                          '--scenario',str(ROOT/'assets/shot-chain-example.json')],capture_output=True,text=True,check=True)
        rows=[json.loads(x) for x in p.stdout.splitlines()]
        self.assertTrue(all(r['ok'] for r in rows))
        self.assertEqual(rows[-1]['result']['state'],rows[-2]['result']['state'])
        chain=rows[-1]['result']['state']['shot_chain']
        self.assertEqual(chain['nodes']['execution-node']['status'],'superseded')
        self.assertEqual(chain['nodes']['fix-node']['value']['club'],'9i')
        self.assertIsNone(chain['shots']['s1']['stroke_number'])
    def test_invalid_input_rejects_without_stopping_stream(self):
        p=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/shot_chain_cli.py')],
          input='{}\n{"action":"create"}\n',capture_output=True,text=True,check=True)
        rows=[json.loads(x) for x in p.stdout.splitlines()]
        self.assertEqual(rows[0]['result']['action'],'reject');self.assertTrue(rows[1]['ok'])
