"""Offline regression coverage using the actual V2 fixtures."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks.evaluate_v2 import evaluate
from benchmarks.live_v2 import run
from benchmarks.quality_gate import evaluate_case, run_gate

FIXTURES = Path(__file__).resolve().parents[1] / 'benchmarks/fixtures/market_cases_v2.json'


def report_for(case):
    return {
        'analysis_summary': 'Synthetic data only', 'operation_advice': 'Observe',
        'sentiment_score': 50,
        'dashboard': {'core_conclusion': {'one_sentence': 'Synthetic case'}},
        'benchmark_observations': {k: case[k] for k in ('stock_code', 'as_of_date', 'close', 'change_pct')},
    }


class BenchmarkV2Tests(unittest.TestCase):
    def setUp(self):
        self.fixtures = json.loads(FIXTURES.read_text())
        self.case = self.fixtures['cases'][0]

    def test_real_fixture_runner_to_gate(self):
        responses = iter(report_for(c) for c in self.fixtures['cases'])
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'LLM_BENCHMARK_DELAY_SECONDS': '0'}):
            result = run(self.fixtures, ['mock'], 20, Path(folder),
                         caller=lambda m, p: (json.dumps(next(responses)), 10, 20, .01))
            self.assertEqual(result['by_model']['mock']['task_success_rate'], 1)
            self.assertTrue(run_gate(FIXTURES, folder)['passed'])

    def test_strict_validation_agrees_with_gate(self):
        valid = report_for(self.case)
        variants = []
        for field, value in [('sentiment_score', True), ('sentiment_score', '50'),
                             ('analysis_summary', []), ('operation_advice', ' ')]:
            report = copy.deepcopy(valid)
            report[field] = value
            variants.append(report)
        for value in [True, str(self.case['close']), float('nan')]:
            report = copy.deepcopy(valid)
            report['benchmark_observations']['close'] = value
            variants.append(report)
        report = copy.deepcopy(valid)
        del report['benchmark_observations']['close']
        variants.append(report)
        report = copy.deepcopy(valid)
        report['dashboard']['core_conclusion'] = []
        variants.append(report)
        for report in [valid] + variants:
            with self.subTest(report=report):
                result = evaluate(self.fixtures, [{'model': 'm', 'case_id': self.case['case_id'], 'report': report}], [])
                self.assertEqual(result['records'][0]['task_success'], not evaluate_case(report, self.case))

    def test_missing_null_is_not_preserved_null(self):
        case = dict(self.case, close=None)
        report = report_for(case)
        self.assertFalse(evaluate_case(report, case))
        del report['benchmark_observations']['close']
        result = evaluate({'cases': [case]}, [{'model': 'm', 'case_id': case['case_id'], 'report': report}], [])
        self.assertFalse(result['records'][0]['task_success'])

    def test_cost_includes_invalid_response(self):
        usage = [{'model': 'm', 'case_id': self.case['case_id'], 'estimated_cost_usd': .1, 'input_tokens': 10},
                 {'model': 'm', 'case_id': 'failed', 'estimated_cost_usd': .2, 'input_tokens': 20}]
        result = evaluate(self.fixtures, [{'model': 'm', 'case_id': self.case['case_id'], 'report': report_for(self.case)}], usage)
        summary = result['by_model']['m']
        self.assertAlmostEqual(summary['total_cost_usd'], .3)
        self.assertAlmostEqual(summary['cost_per_success_usd'], .3)
        self.assertEqual(summary['input_tokens'], 30)

    def test_success_and_api_failure_have_incomplete_cost(self):
        result = evaluate(self.fixtures,
                          [{'model': 'm', 'case_id': self.case['case_id'], 'report': report_for(self.case)}],
                          [{'model': 'm', 'case_id': self.case['case_id'], 'estimated_cost_usd': .1}],
                          errors=[{'model': 'm', 'case_id': 'failed', 'error_type': 'TimeoutError'}])
        summary = result['by_model']['m']
        self.assertIsNone(summary['total_cost_usd'])
        self.assertEqual(summary['known_cost_usd'], .1)

    def test_all_failed_model_and_unknown_cost_remain_visible(self):
        result = evaluate(self.fixtures, [], [], models=['m'],
                          errors=[{'model': 'm', 'case_id': 'failed', 'error_type': 'TimeoutError'}])
        summary = result['by_model']['m']
        self.assertEqual(summary['evaluated_cases'], 0)
        self.assertIsNone(summary['task_success_rate'])
        self.assertIsNone(summary['total_cost_usd'])
        self.assertFalse(summary['cost_complete'])


if __name__ == '__main__':
    unittest.main()
