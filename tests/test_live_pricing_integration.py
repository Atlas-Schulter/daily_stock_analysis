"""Ensure the Live Benchmark routes cost computation to the shared estimator."""

import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.live_v2 import run


class LivePricingIntegrationTests(unittest.TestCase):
    def test_one_mock_case_is_priced_and_scored(self):
        case = {
            'case_id': 'c1', 'category': 'normal', 'stock_code': 'NVDA',
            'as_of_date': '2026-01-15', 'close': 120, 'change_pct': -6,
        }
        report = {
            'analysis_summary': 'sample', 'operation_advice': 'observe',
            'sentiment_score': 50,
            'dashboard': {'core_conclusion': {'one_sentence': 'sample'}},
            'benchmark_observations': {
                key: case[key] for key in
                ('stock_code', 'as_of_date', 'close', 'change_pct')
            },
        }
        with tempfile.TemporaryDirectory() as folder:
            result = run(
                {'cases': [case]}, ['aihubmix/deepseek-v4.1-flash'], 1,
                Path(folder), caller=lambda model, prompt: (json.dumps(report), 1000, 500, None),
            )
            usage = json.loads((Path(folder) / 'usage.jsonl').read_text().strip())
            self.assertEqual(result['evaluated_records'], 1)
            self.assertEqual(usage['pricing_status'], 'estimated')
            self.assertIn(usage['pricing_tier'], ('peak', 'offpeak'))
            self.assertGreater(usage['estimated_cost_usd'], 0)
            self.assertTrue(result['by_model']['aihubmix/deepseek-v4.1-flash']['cost_complete'])


if __name__ == '__main__':
    unittest.main()
