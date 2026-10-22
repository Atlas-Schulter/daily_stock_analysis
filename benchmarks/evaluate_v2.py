"""Offline evaluation of stored LLM benchmark outputs; no API calls."""
import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

REQUIRED = ('analysis_summary', 'operation_advice', 'sentiment_score')

def load_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]

def structure_ok(report):
    if not isinstance(report, dict): return False
    if any(report.get(k) is None or report.get(k) == '' for k in REQUIRED): return False
    core = report.get('dashboard', {}).get('core_conclusion', {}) if isinstance(report.get('dashboard'),dict) else {}
    if not isinstance(core,dict) or not core.get('one_sentence'): return False
    try: return 0 <= float(report['sentiment_score']) <= 100
    except (TypeError, ValueError): return False

def equal_num(a,b, tolerance=1e-6):
    if a is None or b is None: return a is None and b is None
    try: return math.isclose(float(a),float(b),rel_tol=0,abs_tol=tolerance)
    except (TypeError,ValueError): return False

def check_facts(case,report):
    """Only check explicitly structured benchmark_observations; no free-text fact claims."""
    obs=report.get('benchmark_observations') if isinstance(report,dict) else None
    if not isinstance(obs,dict):return 0, 0, ['missing_benchmark_observations']
    pairs=[('stock_code',case['stock_code']),('as_of_date',case['as_of_date']),('close',case['close']),('change_pct',case['change_pct'])]
    errors=[]
    for key,expected in pairs:
        actual=obs.get(key)
        matches=equal_num(actual,expected) if key in ('close','change_pct') else actual==expected
        if not matches:errors.append(key)
    return len(pairs),len(pairs)-len(errors),errors

def percentile(values,p):
    if not values:return None
    vals=sorted(values);idx=(len(vals)-1)*p;lo=math.floor(idx);hi=math.ceil(idx)
    return round(vals[lo]+(vals[hi]-vals[lo])*(idx-lo),3)

def evaluate(fixtures,reports,usage):
    cases={c['case_id']:c for c in fixtures['cases']}
    usage_map={(u['case_id'],u['model']):u for u in usage}
    rows=[]
    for item in reports:
        case=cases.get(item.get('case_id'))
        if case is None: continue
        model=item['model']; report=item.get('report'); token=usage_map.get((item['case_id'],model),{})
        n,correct,errors=check_facts(case,report)
        structurally_ok=structure_ok(report)
        complete=structurally_ok and n==4 and correct==4
        it=token.get('input_tokens');ot=token.get('output_tokens');cost=token.get('estimated_cost_usd')
        row={'case_id':item['case_id'],'category':case['category'],'model':model,
             'structure_passed':structurally_ok,'fact_checked':n,'fact_correct':correct,
             'fact_issues':errors,'task_success':complete,
             'input_tokens':it,'output_tokens':ot,'usage_missing':it is None or ot is None,
             'latency_seconds':token.get('latency_seconds'),'estimated_cost_usd':cost}
        rows.append(row)
    grouped=defaultdict(list)
    for row in rows:grouped[row['model']].append(row)
    summary={}
    for model,records in grouped.items():
        count=len(records);checked=sum(r['fact_checked'] for r in records);correct=sum(r['fact_correct'] for r in records)
        latencies=[float(r['latency_seconds']) for r in records if r['latency_seconds'] is not None]
        successes=sum(r['task_success'] for r in records)
        costs=[r['estimated_cost_usd'] for r in records]
        cost_complete=all(x is not None for x in costs)
        summary[model]={'evaluated_cases':count,'fixture_coverage':f'{count}/{len(cases)}',
           'structural_pass_rate':round(sum(r['structure_passed'] for r in records)/count,4),
           'data_consistency_rate':round(correct/checked,4) if checked else None,
           'verifiable_fact_error_rate':round((checked-correct)/checked,4) if checked else None,
           'task_success_rate':round(successes/count,4),
           'missing_usage_rate':round(sum(r['usage_missing'] for r in records)/count,4),
           'latency_p50_seconds':percentile(latencies,.5),'latency_p95_seconds':percentile(latencies,.95),
           'input_tokens':sum(r['input_tokens'] or 0 for r in records),
           'output_tokens':sum(r['output_tokens'] or 0 for r in records),
           'cost_complete':cost_complete,
           'total_cost_usd':round(sum(costs),8) if cost_complete else None,
           'cost_per_success_usd':round(sum(costs)/successes,8) if cost_complete and successes else None}
    return {'schema_version':2,'fixture_cases':len(cases),'evaluated_records':len(rows),'by_model':summary,'records':rows,
            'notes':['Metrics use only submitted sample reports, not fabricated outputs for remaining fixtures.',
                     'Data consistency checks only structured observations, not narrative statements.',
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
