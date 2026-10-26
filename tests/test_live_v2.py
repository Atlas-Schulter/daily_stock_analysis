import json
import tempfile
import unittest
from pathlib import Path
from benchmarks.live_v2 import decode_report, run, make_prompt

class LiveV2Tests(unittest.TestCase):
    def setUp(self):
        self.case={'case_id':'c1','category':'normal','stock_code':'NVDA','as_of_date':'2026-01-15','close':120,'change_pct':-6}
        self.fixtures={'cases':[self.case]}
    def response(self):
        r={'analysis_summary':'sample','operation_advice':'observe','sentiment_score':50,
           'dashboard':{'core_conclusion':{'one_sentence':'sample'}},
           'benchmark_observations':{k:self.case[k] for k in ['stock_code','as_of_date','close','change_pct']}}
        return json.dumps(r),100,50,None
    def test_one_mock_call_produces_scored_artifacts(self):
        with tempfile.TemporaryDirectory() as folder:
            result=run(self.fixtures,['aihubmix/example'],1,Path(folder),caller=lambda m,p:self.response())
            self.assertEqual(result['evaluated_records'],1)
            self.assertEqual(result['by_model']['aihubmix/example']['task_success_rate'],1)
            self.assertTrue((Path(folder)/'benchmark_comparison.json').exists())
    def test_max_calls_blocks_before_call(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                run(self.fixtures,['a','b'],1,Path(folder),caller=lambda m,p:self.response())
    def test_failed_call_does_not_fabricate_report(self):
        def fail(m,p): raise RuntimeError('simulated provider error')
        with tempfile.TemporaryDirectory() as folder:
            result=run(self.fixtures,['model'],1,Path(folder),caller=fail)
            self.assertEqual(result['evaluated_records'],0)
            self.assertEqual(result['failed_calls'],1)
            self.assertEqual(len((Path(folder)/'errors.jsonl').read_text().splitlines()),1)
    def test_markdown_fenced_json(self):
        self.assertEqual(decode_report('```json\n{"a": 1}\n```'),{'a':1})
    def test_prompt_has_explicit_flat_to_nested_mapping(self):
        case = dict(self.case, change_pct=None)
        prompt = make_prompt(case)
        self.assertIn('TOP-LEVEL', prompt)
        self.assertIn('NEVER an array or string', prompt)
        self.assertIn('preserving null as null', prompt)
        payload = json.loads(prompt.split('Synthetic input fixture: ', 1)[1])
        self.assertEqual(payload, case)
        from benchmarks.live_v2 import PROMPT_VERSION
        self.assertEqual(PROMPT_VERSION, 'frozen-market-v2.1')



class LiveV2RegressionTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        self.env = patch.dict('os.environ', {'LLM_BENCHMARK_DELAY_SECONDS': '0', 'LLM_BENCHMARK_MAX_TOKENS': '4096'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.output = Path(self.folder.name)
        self.fixtures = {'cases': [dict(case_id=f'c{i}', category='normal', stock_code='NVDA',
                                        as_of_date='2026-01-01', close=1, change_pct=None) for i in range(3)]}

    def response(self, model, prompt):
        case = self.fixtures['cases'][0]
        report = {'analysis_summary': 'Synthetic', 'operation_advice': 'Observe', 'sentiment_score': 50,
                  'dashboard': {'core_conclusion': {'one_sentence': 'Synthetic'}},
                  'benchmark_observations': {k: case[k] for k in ('stock_code', 'as_of_date', 'close', 'change_pct')}}
        return json.dumps(report), 10, 20, .1

    def rows(self, name):
        return [json.loads(line) for line in (self.output / name).read_text().splitlines()]

    def test_invalid_json_keeps_usage_and_cost(self):
        result = run(self.fixtures, ['m'], 3, self.output, caller=lambda m, p: ('{', 10, 20, .1))
        self.assertEqual(len(self.rows('usage.jsonl')), 3)
        self.assertEqual(len(self.rows('reports.jsonl')), 0)
        self.assertEqual(result['failed_calls'], 3)
        self.assertAlmostEqual(result['by_model']['m']['total_cost_usd'], .3)

    def test_rate_limit_skips_only_current_model(self):
        class Throttled(Exception):
            status_code = 429
        calls = []
        def caller(model, prompt):
            calls.append(model)
            if model == 'limited':
                raise Throttled('Quota')
            return self.response(model, prompt)
        result = run(self.fixtures, ['limited', 'healthy'], 6, self.output, caller=caller)
        self.assertEqual(calls, ['limited', 'healthy', 'healthy', 'healthy'])
        self.assertEqual((result['planned_calls'], result['attempted_calls'], result['failed_calls'],
                          result['skipped_calls'], result['successful_calls']), (6, 4, 1, 2, 3))
        self.assertEqual(result['call_success_rate'], .5)
        self.assertEqual(result['attempt_success_rate'], .75)
        self.assertIn('limited', result['by_model'])
        self.assertEqual(sum(r['error_type'] == 'SkippedAfterRateLimit' for r in self.rows('errors.jsonl')), 2)

    def test_unrelated_429_text_does_not_skip(self):
        def caller(model, prompt):
            raise ValueError('Invalid JSON at character 429')
        result = run(self.fixtures, ['m'], 3, self.output, caller=caller)
        self.assertEqual(result['attempted_calls'], 3)
        self.assertEqual(result['skipped_calls'], 0)

    def test_pricing_failure_keeps_report_and_usage(self):
        from unittest.mock import patch
        with patch('benchmarks.live_v2.estimate_cost', side_effect=ValueError('bad config')):
            result = run(self.fixtures, ['m'], 3, self.output,
                         caller=lambda m, p: (self.response(m, p)[0], 10, 20, None))
        self.assertEqual(result['successful_calls'], 3)
        self.assertTrue(all(r['pricing_status'] == 'unpriced' for r in self.rows('usage.jsonl')))

    def test_invalid_settings_rejected_before_call_or_overwrite(self):
        from unittest.mock import Mock, patch
        artifact = self.output / 'reports.jsonl'
        artifact.write_text('existing')
        for key, value in [('LLM_BENCHMARK_DELAY_SECONDS', 'nan'), ('LLM_BENCHMARK_DELAY_SECONDS', '-1'),
                           ('LLM_BENCHMARK_MAX_TOKENS', '0')]:
            caller = Mock()
            with self.subTest(key=key, value=value), patch.dict('os.environ', {key: value}):
                with self.assertRaises(ValueError):
                    run(self.fixtures, ['m'], 3, self.output, caller=caller)
            caller.assert_not_called()
            self.assertEqual(artifact.read_text(), 'existing')

    def test_delay_between_calls_including_model_boundary(self):
        from unittest.mock import patch
        with patch.dict('os.environ', {'LLM_BENCHMARK_DELAY_SECONDS': '5'}), patch('benchmarks.live_v2.time.sleep') as sleep, patch('benchmarks.live_v2.time.monotonic', side_effect=[0, 1, 6, 7]):
            run(self.fixtures, ['a', 'b'], 2, self.output, caller=self.response, sample_limit=1)
        sleep.assert_called_once_with(5)
        self.assertEqual([r['latency_seconds'] for r in self.rows('usage.jsonl')], [1, 1])

    def test_provider_parameters_and_four_field_contract(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from benchmarks.live_v2 import call_model
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'), finish_reason='stop')],
                                   usage=SimpleNamespace(prompt_tokens=10, completion_tokens=20))
        client = SimpleNamespace(completion=Mock(return_value=response))
        with patch.dict(sys.modules, {'litellm': client}), patch.dict('os.environ', {'LLM_BENCHMARK_MAX_TOKENS': '2048'}):
            self.assertEqual(call_model('gemini/test', 'prompt'), ('{}', 10, 20, None))
            args = client.completion.call_args.kwargs
            self.assertEqual(args['max_tokens'], 2048)
            self.assertEqual(args['response_format'], {'type': 'json_object'})
            self.assertEqual(args['num_retries'], 0)
            call_model('openai/test', 'prompt')
            self.assertNotIn('response_format', client.completion.call_args.kwargs)


if __name__ == '__main__':
    unittest.main()
