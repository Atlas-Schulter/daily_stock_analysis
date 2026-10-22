"""Offline, deterministic benchmark for LLM stock reports; no network or model calls."""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from src.llmops_metrics import evaluate_report


def load_jsonl(path):
    p = Path(path)
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]


def check_market_facts(report, fixture):
    """Compare explicitly declared observations to the same-date reference fixture.

    A missing observation is NOT a factual match; it is 'not evaluated'.
    Fields are benchmark metadata, not guessed from Chinese natural-language prose.
    """
    observed = report.get('benchmark_observations') or {}
    if not isinstance(observed, dict):
        return {'status': 'fail', 'checked': 0, 'issues': ['benchmark_observations:not_object']}
    required = ('stock_code', 'as_of_date', 'close', 'change_pct')
    absent = [k for k in required if k not in observed]
    if absent:
        return {'status': 'not_evaluated', 'checked': 0, 'issues': [f'{k}:missing' for k in absent]}
    issues = []
    checked = 0
    for field in ('stock_code', 'as_of_date'):
        checked += 1
        if str(observed[field]) != str(fixture[field]):
            issues.append(f'{field}:mismatch')
    for field, tolerance in (('close', 0.01), ('change_pct', 0.02)):
        checked += 1
        try:
            measured = float(observed[field]); expected = float(fixture[field])
            if not (math.isfinite(measured) and abs(measured - expected) <= tolerance):
                issues.append(f'{field}:mismatch')
        except (ValueError, TypeError):
            issues.append(f'{field}:invalid')
    return {'status': 'fail' if issues else 'pass', 'checked': checked, 'issues': issues}


def benchmark(reports, fixtures, usages):
    fixtures_by_id = {f['case_id']: f for f in fixtures}
    usage_by_id = defaultdict(list)
    for u in usages:
        if u.get('case_id') is not None and u.get('model') is not None:
            usage_by_id[(str(u['case_id']), str(u['model']))].append(u)
    records = []
    for sample in reports:
        case_id, model = str(sample['case_id']), str(sample['model'])
        if case_id not in fixtures_by_id:
            raise ValueError(f'Missing fixture for case_id={case_id}')
        report = sample['report']
        structure = evaluate_report(report)
        facts = check_market_facts(report, fixtures_by_id[case_id])
        usage_rows = usage_by_id[(case_id, model)]
        costs = [r.get('estimated_cost_usd') for r in usage_rows]
        priced = bool(usage_rows) and all(v is not None for v in costs)
        records.append({
            'case_id': case_id, 'model': model,
            'structure_passed': structure['passed'],
            'missing_fields': structure['missing_fields'],
            'facts_status': facts['status'], 'facts_checked': facts['checked'],
            'fact_issues': facts['issues'],
            'llm_calls': len(usage_rows),
            'input_tokens': sum(int(r.get('input_tokens') or 0) for r in usage_rows),
            'output_tokens': sum(int(r.get('output_tokens') or 0) for r in usage_rows),
            'estimated_cost_usd': round(sum(float(v) for v in costs), 8) if priced else None,
            'cost_status': 'priced' if priced else 'unpriced_or_missing',
        })
    by_model = {}
    for model in sorted({r['model'] for r in records}):
        rs = [r for r in records if r['model'] == model]
        n = len(rs)
        assessed = [r for r in rs if r['facts_status'] != 'not_evaluated']
        complete_cost = all(r['cost_status'] == 'priced' for r in rs)
        by_model[model] = {
            'cases': n,
            'structure_pass_rate': round(sum(r['structure_passed'] for r in rs) / n, 4),
            'fact_evaluated_cases': len(assessed),
            'fact_pass_rate_on_evaluated': round(sum(r['facts_status'] == 'pass' for r in assessed) / len(assessed), 4) if assessed else None,
            'llm_calls': sum(r['llm_calls'] for r in rs),
            'input_tokens': sum(r['input_tokens'] for r in rs),
            'output_tokens': sum(r['output_tokens'] for r in rs),
            'estimated_cost_usd': round(sum(r['estimated_cost_usd'] for r in rs), 8) if complete_cost else None,
            'cost_complete': complete_cost,
        }
    return {'benchmark_version': 1, 'note': 'Structural checks plus explicit benchmark observations; no semantic fact-checking of narrative text.', 'records': records, 'by_model': by_model}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', default='benchmarks/fixtures/market_cases.json')
    parser.add_argument('--reports', default='benchmarks/samples/reports.jsonl')
    parser.add_argument('--usage', default='benchmarks/samples/usage.jsonl')
    parser.add_argument('--output', default='artifacts/llm_benchmark.json')
    args = parser.parse_args()
    fixtures = json.loads(Path(args.fixtures).read_text(encoding='utf-8'))
    reports = load_jsonl(args.reports)
    usages = load_jsonl(args.usage)
    if not reports:
        raise SystemExit('No benchmark report samples; supply real model outputs or use provided fixture sample')
    result = benchmark(reports, fixtures, usages)
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['by_model'], ensure_ascii=False, indent=2))
    print(f'Benchmark saved: {out}')


if __name__ == '__main__':
    main()
