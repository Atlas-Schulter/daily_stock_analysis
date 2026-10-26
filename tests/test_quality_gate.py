import json
import tempfile
import unittest
from pathlib import Path
from benchmarks.quality_gate import run_gate, evaluate_case


class QualityGateTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.fixtures = self.root / 'fixtures.json'
        self.case = {'case_id': 'c1', 'benchmark_observations': {'stock_code': 'NVDA', 'as_of_date': '2026-01-01', 'close': 100.0, 'change_pct': None}}
        self.fixtures.write_text(json.dumps({'cases': [self.case]}))
        self.report = {'analysis_summary': 'Valid', 'operation_advice': 'Caution', 'sentiment_score': 55, 'dashboard': {'core_conclusion': {'one_sentence': 'Test conclusion'}}, 'benchmark_observations': dict(self.case['benchmark_observations'])}
        self.write('reports.jsonl', [{'model': 'mock', 'case_id': 'c1', 'report': self.report}])
        self.write('usage.jsonl', [{'model': 'mock', 'case_id': 'c1', 'input_tokens': 10, 'output_tokens': 20, 'estimated_cost_usd': None}])
        self.write('errors.jsonl', [])

    def write(self, filename, rows):
        (self.root / filename).write_text(''.join(json.dumps(row) + '\n' for row in rows))

    def test_happy_path(self):
        self.assertTrue(run_gate(self.fixtures, self.root)['passed'])

    def test_wrong_numeric_value_fails(self):
        self.report['benchmark_observations']['close'] = 101
        self.write('reports.jsonl', [{'model': 'mock', 'case_id': 'c1', 'report': self.report}])
        self.assertFalse(run_gate(self.fixtures, self.root)['passed'])

    def test_missing_report_fails_closed(self):
        self.write('reports.jsonl', [])
        with self.assertRaises(ValueError):
            run_gate(self.fixtures, self.root)

    def test_api_error_fails(self):
        self.write('errors.jsonl', [{'model': 'mock', 'case_id': 'c1', 'error_type': 'RateLimitError'}])
        self.assertFalse(run_gate(self.fixtures, self.root)['passed'])

    def test_unknown_cost_allowed_unless_required(self):
        self.assertTrue(run_gate(self.fixtures, self.root)['passed'])
        self.assertFalse(run_gate(self.fixtures, self.root, require_pricing=True)['passed'])

    def test_null_preserved(self):
        self.report['benchmark_observations']['change_pct'] = 0
        self.assertIn('mismatch:change_pct', evaluate_case(self.report, self.case))


if __name__ == '__main__':
    unittest.main()
