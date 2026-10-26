"""Strict offline quality gate for live_v2 artifacts. Python standard library only."""
import argparse
import json
import math
from pathlib import Path

REQUIRED = ('analysis_summary', 'operation_advice', 'sentiment_score')


def read_jsonl(path):
    if not path.is_file():
        raise ValueError(f'Missing file: {path}')
    rows = []
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f'Invalid JSONL at {path}:{number}: {exc.msg}') from exc
    return rows


def same_number(observed, expected, tolerance=1e-6):
    if isinstance(observed, bool) or isinstance(expected, bool):
        return False
    if not isinstance(observed, (int, float)) or not isinstance(expected, (int, float)):
        return False
    return math.isfinite(observed) and math.isfinite(expected) and math.isclose(observed, expected, rel_tol=0, abs_tol=tolerance)


def evaluate_case(report, fixture):
    problems = []
    if not isinstance(report, dict):
        return ['report_not_object']
    for field in REQUIRED:
        if field not in report:
            problems.append('missing:' + field)
    if not isinstance(report.get('analysis_summary'), str) or not report.get('analysis_summary', '').strip():
        problems.append('invalid:analysis_summary')
    if not isinstance(report.get('operation_advice'), str) or not report.get('operation_advice', '').strip():
        problems.append('invalid:operation_advice')
    sentiment = report.get('sentiment_score')
    if isinstance(sentiment, bool) or not isinstance(sentiment, (int, float)) or not (0 <= sentiment <= 100):
        problems.append('invalid:sentiment_score')
    dashboard = report.get('dashboard')
    sentence = dashboard.get('core_conclusion', {}).get('one_sentence') if isinstance(dashboard, dict) and isinstance(dashboard.get('core_conclusion'), dict) else None
    if not isinstance(sentence, str) or not sentence.strip():
        problems.append('invalid:dashboard.core_conclusion.one_sentence')
    expected = fixture.get('benchmark_observations')
    actual = report.get('benchmark_observations')
    if not isinstance(expected, dict):
        problems.append('fixture_missing:benchmark_observations')
    elif not isinstance(actual, dict):
        problems.append('invalid:benchmark_observations')
    else:
        for key in ('stock_code', 'as_of_date', 'close', 'change_pct'):
            x, y = actual.get(key), expected.get(key)
            if key not in actual or key not in expected:
                problems.append('missing_observation:' + key)
            elif x is None or y is None:
                if x is not None or y is not None:
                    problems.append('mismatch:' + key)
            elif key in ('close', 'change_pct'):
                if not same_number(x, y):
                    problems.append('mismatch:' + key)
            elif type(x) is not type(y) or x != y:
                problems.append('mismatch:' + key)
    return sorted(set(problems))


def run_gate(fixtures_path, artifacts_dir, min_pass_rate=1.0, require_pricing=False, sample_limit=None):
    fixtures = json.loads(Path(fixtures_path).read_text(encoding='utf-8'))
    cases = fixtures.get('cases', [])
    if sample_limit is not None:
        cases = cases[:sample_limit]
    if not cases:
        raise ValueError('Fixture cases are empty')
    case_map = {case['case_id']: case for case in cases}
    if len(case_map) != len(cases):
        raise ValueError('Duplicate case_id in fixtures')
    base = Path(artifacts_dir)
    reports = read_jsonl(base / 'reports.jsonl')
    usages = read_jsonl(base / 'usage.jsonl')
    errors = read_jsonl(base / 'errors.jsonl')
    if not reports:
        raise ValueError('No model reports: fail closed')
    models = set()
    for row in reports + usages + errors:
        if row.get('model'):
            models.add(row['model'])
    if not models:
        raise ValueError('No model identified')
    expected_pairs = {(model, case_id) for model in models for case_id in case_map}
    reports_by_pair = {}
    for row in reports:
        pair = (row.get('model'), row.get('case_id'))
        if pair in reports_by_pair:
            raise ValueError(f'Duplicate model/case report: {pair}')
        reports_by_pair[pair] = row['report']
    usage_by_pair = {}
    for row in usages:
        pair = (row.get('model'), row.get('case_id'))
        if pair in usage_by_pair:
            raise ValueError(f'Duplicate usage entry: {pair}')
        usage_by_pair[pair] = row
    details = []
    passed = 0
    for model, case_id in sorted(expected_pairs):
        pair = (model, case_id)
        problems = []
        if pair not in reports_by_pair:
            problems.append('missing_report')
        else:
            problems.extend(evaluate_case(reports_by_pair[pair], case_map[case_id]))
        usage = usage_by_pair.get(pair)
        if not usage:
            problems.append('missing_usage')
        else:
            for field in ('input_tokens', 'output_tokens'):
                value = usage.get(field)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    problems.append('invalid:' + field)
            cost = usage.get('estimated_cost_usd')
            if require_pricing and (not isinstance(cost, (int, float)) or isinstance(cost, bool) or not math.isfinite(cost) or cost < 0):
                problems.append('missing_price')
        if not problems:
            passed += 1
        details.append({'model': model, 'case_id': case_id, 'passed': not problems, 'issues': sorted(set(problems))})
    # Errors are failures irrespective of whether a report exists.
    actual_errors = [e for e in errors if e.get('error_type') != 'SkippedAfterRateLimit']
    rate = passed / len(expected_pairs)
    ok = not actual_errors and not errors and rate >= min_pass_rate
    return {
        'passed': ok, 'pass_rate': round(rate, 4), 'minimum_pass_rate': min_pass_rate,
        'expected_pairs': len(expected_pairs), 'quality_passed_pairs': passed,
        'error_rows': len(errors), 'unpriced_allowed': not require_pricing,
        'details': details,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', default='benchmarks/fixtures/market_cases_v2.json')
    parser.add_argument('--artifacts-dir', default='artifacts/live_v2')
    parser.add_argument('--min-pass-rate', type=float, default=1.0)
    parser.add_argument('--require-pricing', action='store_true')
    parser.add_argument('--sample-limit', type=int, default=None)
    args = parser.parse_args()
    if not 0 < args.min_pass_rate <= 1:
        parser.error('--min-pass-rate must be in (0, 1]')
    out = Path(args.artifacts_dir)
    try:
        result = run_gate(args.fixtures, out, args.min_pass_rate, args.require_pricing, args.sample_limit)
    except (ValueError, OSError, KeyError) as exc:
        result = {'passed': False, 'reason': str(exc)}
    out.mkdir(parents=True, exist_ok=True)
    (out / 'quality_gate.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
