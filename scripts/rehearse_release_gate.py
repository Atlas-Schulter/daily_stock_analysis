"""Generate explicitly synthetic release-gate rehearsal evidence; never call APIs."""
import argparse
import json
from pathlib import Path


# 只生成合成报告，给真正的 Gate CLI 使用；不接触 API 或镜像仓库。
# invalid 路径故意改错事实值，验证的是拦截能力，不是模型生成质量。
def generate(scenario, output):
    fixtures = json.loads(Path('benchmarks/fixtures/market_cases_v2.json').read_text())
    output.mkdir(parents=True, exist_ok=True)
    reports, usage = [], []
    for case in fixtures['cases'][:2]:
        observations = {k: case[k] for k in ('stock_code', 'as_of_date', 'close', 'change_pct')}
        # 保持所有字段完整，只破坏一个数值，让失败原因明确且可复现。
        if scenario == 'invalid':
            observations['close'] = case['close'] + 1
        reports.append({'model': 'synthetic-rehearsal', 'case_id': case['case_id'], 'report': {
            'analysis_summary': 'Synthetic rehearsal, not model evidence',
            'operation_advice': 'Not investment advice', 'sentiment_score': 50,
            'dashboard': {'core_conclusion': {'one_sentence': 'Synthetic rehearsal'}},
            'benchmark_observations': observations,
        }})
        usage.append({'model': 'synthetic-rehearsal', 'case_id': case['case_id'],
                      'input_tokens': 0, 'output_tokens': 0, 'estimated_cost_usd': None})
    for name, rows in [('reports', reports), ('usage', usage), ('errors', [])]:
        (output / f'{name}.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (output / 'provenance.json').write_text(json.dumps({'mode': 'synthetic-rehearsal', 'scenario': scenario}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--scenario', choices=['valid', 'invalid'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    generate(args.scenario, args.output)
