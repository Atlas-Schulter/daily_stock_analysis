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
    def test_prompt_has_fixture(self):
        self.assertIn('NVDA',make_prompt(self.case))

if __name__=='__main__': unittest.main()
