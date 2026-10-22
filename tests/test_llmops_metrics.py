import tempfile
import unittest
from pathlib import Path
from src.llmops_metrics import record_usage, summarize_usage, evaluate_report, record_evaluation


class TestLLMOpsMetrics(unittest.TestCase):
    def test_usage_and_cost(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'calls.jsonl'
            row = record_usage({'prompt_tokens': 1000, 'completion_tokens': 200},
                               'demo-model', 'analysis', 'NVDA', path,
                               {'demo-model': {'input_per_million': 1, 'output_per_million': 3}})
            self.assertEqual(row['estimated_cost_usd'], 0.0016)
            summary = summarize_usage(path)
            self.assertEqual(summary['calls'], 1)
            self.assertTrue(summary['cost_complete'])
            self.assertEqual(summary['by_model']['demo-model']['input_tokens'], 1000)

    def test_unknown_price_not_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'calls.jsonl'
            row = record_usage({'prompt_tokens': 10}, 'other', 'analysis', output=path)
            self.assertIsNone(row['estimated_cost_usd'])
            self.assertFalse(summarize_usage(path)['cost_complete'])

    def test_report_evaluation(self):
        good = {'analysis_summary': 'sample', 'operation_advice': 'hold',
                'sentiment_score': 50,
                'dashboard': {'core_conclusion': {'one_sentence': 'example'}}}
        self.assertTrue(evaluate_report(good)['passed'])
        self.assertFalse(evaluate_report({'sentiment_score': 120})['passed'])

    def test_persist_quality(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'eval.jsonl'
            row = record_evaluation({'sentiment_score': 120}, 'demo', 'NVDA', path)
            self.assertFalse(row['passed'])
            self.assertIn('sentiment_score:out_of_range', row['missing_fields'])

    def test_no_raw_prompt_in_record(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'calls.jsonl'
            record_usage({}, 'demo', 'analysis', output=path)
            self.assertNotIn('prompt', path.read_text().replace('prompt_tokens', ''))

if __name__ == '__main__':
    unittest.main()
