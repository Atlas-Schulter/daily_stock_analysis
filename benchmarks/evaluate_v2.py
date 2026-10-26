"""Offline evaluation of stored LLM benchmark outputs; no API calls."""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from benchmarks.quality_gate import evaluate_case

def load_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]

def structure_ok(report):
    problems = evaluate_case(report, {})
    return not any(p == 'report_not_object' or p.startswith(('missing:', 'invalid:'))
                   and p != 'invalid:benchmark_observations' for p in problems)


def check_facts(case, report):
    """Use the same strict observation checks as the quality gate."""
    obs = report.get('benchmark_observations') if isinstance(report, dict) else None
    if not isinstance(obs, dict):
        return 0, 0, ['missing_benchmark_observations']
    problems = evaluate_case(report, case)
    errors = [p.split(':', 1)[1] for p in problems
              if p.startswith(('mismatch:', 'missing_observation:'))]
    return 4, 4 - len(errors), errors

def percentile(values,p):
    if not values:return None
    vals=sorted(values);idx=(len(vals)-1)*p;lo=math.floor(idx);hi=math.ceil(idx)
    return round(vals[lo]+(vals[hi]-vals[lo])*(idx-lo),3)

def evaluate(fixtures,reports,usage,models=None,errors=None):
    cases={c['case_id']:c for c in fixtures['cases']}
    usage_map={(u['case_id'],u['model']):u for u in usage}
    rows=[]
    for item in reports:
        case=cases.get(item.get('case_id'))
        if case is None: continue
        model=item['model']; report=item.get('report'); token=usage_map.get((item['case_id'],model),{})
        n,correct,fact_errors=check_facts(case,report)
        structurally_ok=structure_ok(report)
        complete=structurally_ok and n==4 and correct==4
        it=token.get('input_tokens');ot=token.get('output_tokens');cost=token.get('estimated_cost_usd')
        row={'case_id':item['case_id'],'category':case['category'],'model':model,
             'structure_passed':structurally_ok,'fact_checked':n,'fact_correct':correct,
             'fact_issues':fact_errors,'task_success':complete,
             'input_tokens':it,'output_tokens':ot,'usage_missing':it is None or ot is None,
             'latency_seconds':token.get('latency_seconds'),'estimated_cost_usd':cost}
        rows.append(row)
    grouped=defaultdict(list)
    for row in rows:grouped[row['model']].append(row)
    for model in list(models or []) + [u['model'] for u in usage] + [e['model'] for e in (errors or [])]:
        grouped[model]
    summary={}
    for model,records in grouped.items():
        count=len(records);checked=sum(r['fact_checked'] for r in records);correct=sum(r['fact_correct'] for r in records)
        model_usage = [u for u in usage if u['model'] == model]
        latencies=[float(u['latency_seconds']) for u in model_usage if u.get('latency_seconds') is not None]
        successes=sum(r['task_success'] for r in records)
        costs=[u.get('estimated_cost_usd') for u in model_usage]
        usage_pairs = {(u['model'], u['case_id']) for u in model_usage}
        missing_report_usage = any((model, r['case_id']) not in usage_pairs for r in records)
        unknown_failed_usage = any(e['model'] == model and e.get('error_type') != 'SkippedAfterRateLimit'
                                   and (model, e['case_id']) not in usage_pairs for e in (errors or []))
        cost_complete=bool(costs) and all(x is not None for x in costs) and not missing_report_usage and not unknown_failed_usage
        summary[model]={'evaluated_cases':count,'fixture_coverage':f'{count}/{len(cases)}',
           'structural_pass_rate':round(sum(r['structure_passed'] for r in records)/count,4) if count else None,
           'data_consistency_rate':round(correct/checked,4) if checked else None,
           'verifiable_fact_error_rate':round((checked-correct)/checked,4) if checked else None,
           'task_success_rate':round(successes/count,4) if count else None,
           'missing_usage_rate':round(sum(r['usage_missing'] for r in records)/count,4) if count else None,
           'latency_p50_seconds':percentile(latencies,.5),'latency_p95_seconds':percentile(latencies,.95),
           'input_tokens':sum(u.get('input_tokens') or 0 for u in model_usage),
           'output_tokens':sum(u.get('output_tokens') or 0 for u in model_usage),
           'usage_records':len(model_usage),
           'known_cost_usd':round(sum(c for c in costs if c is not None),8),
           'cost_complete':cost_complete,
           'total_cost_usd':round(sum(costs),8) if cost_complete else None,
           'cost_per_success_usd':round(sum(costs)/successes,8) if cost_complete and successes else None}
    return {'schema_version':2,'fixture_cases':len(cases),'evaluated_records':len(rows),'by_model':summary,'records':rows,
            'notes':['Metrics use only submitted sample reports, not fabricated outputs for remaining fixtures.',
                     'Data consistency checks only structured observations, not narrative statements.',
                     'Token, latency and cost metrics include all available usage, including invalid JSON responses.',
                     'Unknown failed-call usage makes total cost incomplete; known_cost_usd is a partial estimate.',
                     'API retry/failure rate requires call-attempt events and is not inferred from successful records.']}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--fixtures',default='benchmarks/fixtures/market_cases_v2.json')
    parser.add_argument('--reports',default='benchmarks/samples/reports.jsonl')
    parser.add_argument('--usage',default='benchmarks/samples/usage.jsonl')
    parser.add_argument('--output',default='artifacts/benchmark_comparison.json')
    args=parser.parse_args()
    result=evaluate(json.loads(Path(args.fixtures).read_text(encoding='utf-8')),load_jsonl(args.reports),load_jsonl(args.usage))
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(result['by_model'],indent=2,ensure_ascii=False))
    print(f'Evaluated {result["evaluated_records"]} report(s) against {result["fixture_cases"]} available fixtures; output: {output}')

if __name__=='__main__':main()
