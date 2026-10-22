import unittest
from src.llm_eval_benchmark import benchmark, check_market_facts

FIXTURE = {'case_id': 'c1', 'stock_code': 'NVDA', 'as_of_date': '2026-01-15', 'close': 120.0, 'change_pct': -6.0}
REPORT = {'analysis_summary': 'test', 'operation_advice': 'test', 'sentiment_score': 40, 'dashboard': {'core_conclusion': {'one_sentence': 'test'}}}


class BenchmarkTests(unittest.TestCase):
    def test_facts_pass(self):
        self.assertEqual(check_market_facts({'benchmark_observations': dict(FIXTURE)}, FIXTURE)['status'], 'pass')

    def test_facts_fail(self):
        observations = dict(FIXTURE, close=999)
        self.assertEqual(check_market_facts({'benchmark_observations': observations}, FIXTURE)['status'], 'fail')

    def test_missing_data_not_evaluated(self):
        self.assertEqual(check_market_facts(REPORT, FIXTURE)['status'], 'not_evaluated')

    def test_missing_cost_is_not_zero(self):
        outcome = benchmark([{'case_id': 'c1', 'model': 'm', 'report': REPORT}], [FIXTURE], [])
        self.assertIsNone(outcome['by_model']['m']['estimated_cost_usd'])
        self.assertIsNone(outcome['by_model']['m']['fact_pass_rate_on_evaluated'])

    def test_mismatched_fixture_rejected(self):
        with self.assertRaises(ValueError):
            benchmark([{'case_id': 'missing', 'model': 'm', 'report': REPORT}], [FIXTURE], [])


if __name__ == '__main__':
    unittest.main()
