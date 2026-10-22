import json
import tempfile
import unittest
from pathlib import Path
from src.llm_eval_live import create_prompt, execute, parse_json_response

CASE = {'case_id': 't', 'stock_code': 'NVDA', 'as_of_date': '2026-01-15', 'close': 120.0, 'change_pct': -6.0}


class LiveHarnessTests(unittest.TestCase):
    def test_fixed_prompt(self):
        self.assertEqual(create_prompt(CASE), create_prompt(dict(reversed(list(CASE.items())))))

    def test_parser(self):
        self.assertEqual(parse_json_response('```json\n{"x": 1}\n```'), {'x': 1})

    def test_case_model_join(self):
        report = {'analysis_summary': 'x', 'operation_advice': 'y', 'sentiment_score': 50,
                  'dashboard': {'core_conclusion': {'one_sentence': 'test'}},
                  'benchmark_observations': {'stock_code': 'NVDA', 'as_of_date': '2026-01-15', 'close': 120, 'change_pct': -6}}
        def fake(model, prompt):
            return {'content': json.dumps(report), 'usage': {'prompt_tokens': 10, 'completion_tokens': 20}, 'estimated_cost_usd': None}
        with tempfile.TemporaryDirectory() as folder:
            reports, usage, errors = execute([CASE], ['mock/a', 'mock/b'], fake, folder)
            r = [json.loads(x) for x in reports.read_text().splitlines()]
            u = [json.loads(x) for x in usage.read_text().splitlines()]
            self.assertEqual({(x['case_id'], x['model']) for x in r}, {('t', 'mock/a'), ('t', 'mock/b')})
            self.assertEqual([x['prompt_sha256'] for x in r], [x['prompt_sha256'] for x in u])
            self.assertEqual(errors.read_text(), '')

    def test_failure_sanitized(self):
        def fail(model, prompt):
            raise RuntimeError('PRIVATE_SECRET')
        with tempfile.TemporaryDirectory() as folder:
            _, _, errors = execute([CASE], ['mock/a'], fail, folder)
            self.assertNotIn('PRIVATE_SECRET', errors.read_text())

    def test_call_cap(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                execute([CASE], ['a', 'b'], lambda *_: {}, folder, max_calls=1)


if __name__ == '__main__':
    unittest.main()
