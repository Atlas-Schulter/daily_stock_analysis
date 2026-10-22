"""Live 20-case LLM Benchmark V2. Only runs after explicit --confirm-live."""
import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from benchmarks.evaluate_v2 import evaluate, load_jsonl

PROMPT_VERSION = "frozen-market-v2"
SYSTEM_MESSAGE = "You are a data fidelity evaluator. Use only the supplied SYNTHETIC case data. Return valid JSON only; no markdown. Never invent missing facts."

def make_prompt(case):
    # Explicit keys, preserves null values in missing-data cases
    payload = json.dumps(case, sort_keys=True, ensure_ascii=False)
    return ("Given the synthetic fixture below, produce JSON fields: analysis_summary (string), "
            "operation_advice (non-personalized cautionary text), sentiment_score (0-100), "
            "dashboard: {core_conclusion: {one_sentence: string}}, "
            "benchmark_observations: {stock_code, as_of_date, close, change_pct}. "
            "Copy the four benchmark_observations exactly from the fixture, including nulls. "
            "If the fixture has missing or inconsistent data, explicitly say so without fabricating a cause. "
            "Synthetic fixture: " + payload)

def decode_report(text):
    if isinstance(text, list):
        text = ''.join(x.get('text', '') for x in text if isinstance(x, dict))
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Empty model content')
    text = text.strip()
    match = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, re.S | re.I)
    if match: text = match.group(1)
    data = json.loads(text)
    if not isinstance(data, dict): raise ValueError('LLM output must be a JSON object')
    return data

def call_model(model, prompt):
    import litellm
    params = {}
    resolved = model
    if model.startswith('aihubmix/'):
        key = os.getenv('AIHUBMIX_API_KEY')
        if not key: raise ValueError('AIHUBMIX_API_KEY is missing')
        resolved = 'openai/' + model[len('aihubmix/'):]
        params.update(api_base='https://aihubmix.com/v1', api_key=key)
    response = litellm.completion(model=resolved,
        messages=[{'role':'system','content':SYSTEM_MESSAGE},{'role':'user','content':prompt}],
        temperature=0, max_tokens=1000, timeout=90, num_retries=0, stream=False, **params)
    usage = getattr(response, 'usage', None)
    input_tokens = getattr(usage, 'prompt_tokens', None)
    output_tokens = getattr(usage, 'completion_tokens', None)
    cost = None
    if not model.startswith('aihubmix/'):
        try:
            candidate = litellm.completion_cost(completion_response=response)
            if candidate is not None: cost = float(candidate)
        except Exception: pass
    return response.choices[0].message.content, input_tokens, output_tokens, cost

def append_jsonl(path, item):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(item, ensure_ascii=False, default=str) + '\n')

def run(fixtures, models, max_calls, output_dir, caller=call_model, sample_limit=None):
    if max_calls < 1: raise ValueError('max_calls must be positive')
    cases = fixtures['cases']
    if sample_limit is not None: cases = cases[:sample_limit]
    planned = len(cases) * len(models)
    if planned > max_calls:
        raise ValueError(f'Plan has {planned} calls; --max-calls={max_calls}. Increase it explicitly or use --sample-limit.')
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_path = output_dir/'reports.jsonl'
    usage_path = output_dir/'usage.jsonl'
    errors_path = output_dir/'errors.jsonl'
    # Each live run writes fresh artifacts. Never silently mix old results.
    for file in (reports_path,usage_path,errors_path): file.write_text('', encoding='utf-8')
    failures = 0
    for model in models:
        for case in cases:
            prompt = make_prompt(case)
            digest = hashlib.sha256((SYSTEM_MESSAGE+'\n'+prompt).encode('utf-8')).hexdigest()
            start = time.monotonic()
            try:
                content, in_tokens, out_tokens, cost = caller(model, prompt)
                latency = round(time.monotonic() - start, 3)
                report = decode_report(content)
                append_jsonl(reports_path, {'case_id':case['case_id'], 'model':model,
                             'report':report, 'prompt_version':PROMPT_VERSION, 'prompt_sha256':digest})
                append_jsonl(usage_path, {'case_id':case['case_id'], 'model':model,
                             'prompt_version':PROMPT_VERSION,'prompt_sha256':digest,
                             'input_tokens':in_tokens,'output_tokens':out_tokens,
                             'estimated_cost_usd':cost,'latency_seconds':latency})
                print(f'OK {model} {case["case_id"]} {latency}s',flush=True)
            except Exception as exc:
                failures += 1
                append_jsonl(errors_path, {'case_id':case['case_id'], 'model':model,
                                        'error_type':type(exc).__name__, 'error_message':str(exc)[:180]})
                print(f'ERROR {model} {case["case_id"]}: {type(exc).__name__}', flush=True)
    results = evaluate(fixtures, load_jsonl(reports_path), load_jsonl(usage_path))
    results['planned_calls'] = planned
    results['failed_calls'] = failures
    results['successful_calls'] = planned-failures
    results['call_success_rate'] = round((planned-failures)/planned,4) if planned else None
    output = output_dir/'benchmark_comparison.json'
    output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'by_model':results['by_model'], 'call_success_rate':results['call_success_rate']}, indent=2))
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', default='benchmarks/fixtures/market_cases_v2.json')
    parser.add_argument('--models', required=True, help='Comma-separated model names')
    parser.add_argument('--max-calls', type=int, default=20)
    parser.add_argument('--sample-limit', type=int, default=None)
    parser.add_argument('--output-dir', default='artifacts/live_v2')
    parser.add_argument('--confirm-live', action='store_true')
    args = parser.parse_args()
    if not args.confirm_live: parser.error('Real API calls require --confirm-live')
    models = [m.strip() for m in args.models.split(',') if m.strip()]
    if not models: parser.error('At least one model is required')
    if args.sample_limit is not None and args.sample_limit < 1: parser.error('--sample-limit must be positive')
    fixtures = json.loads(Path(args.fixtures).read_text(encoding='utf-8'))
    result = run(fixtures, models, args.max_calls, Path(args.output_dir), sample_limit=args.sample_limit)


if __name__ == '__main__': main()
