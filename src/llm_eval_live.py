"""Optional real-model benchmark runner. Never called by push CI."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path


def create_prompt(fixture):
    # Common, frozen input: not a prediction task, and no tools/retrieval.
    payload = {k: fixture[k] for k in ('case_id', 'stock_code', 'as_of_date', 'close', 'change_pct')}
    return (
        'Return ONLY one JSON object, no markdown. Analyze the supplied HISTORICAL fixture, '
        'not live prices. Never invent facts. Required fields: '
        'analysis_summary (string), operation_advice (string), sentiment_score (number 0-100), '
        'dashboard (object with core_conclusion containing one_sentence string), '
        'benchmark_observations (object with stock_code, as_of_date, close, change_pct). '
        'Copy factual numeric values only from the supplied data. '
        'No personalized investment advice. Data: ' + json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def parse_json_response(content):
    if not isinstance(content, str):
        raise ValueError('Model did not return text')
    text = content.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == '```':
            text = '\n'.join(lines[1:-1]).strip()
    obj = json.loads(text)
    if not isinstance(obj, dict):
        raise ValueError('Expected JSON object')
    return obj


def execute(fixtures, models, call, output_dir, max_calls=6):
    """Inject a callable (model, prompt)->response for offline tests; live CLI uses LiteLLM."""
    if len(fixtures) * len(models) > max_calls:
        raise ValueError(f'Refusing {len(fixtures) * len(models)} calls (max {max_calls})')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report_file, usage_file, error_file = [output / n for n in ('reports.jsonl', 'usage.jsonl', 'errors.jsonl')]
    prompt_version = 'frozen-market-v1'
    # Reset outputs to avoid mistakenly combining different runs.
    for path in (report_file, usage_file, error_file):
        path.write_text('', encoding='utf-8')
    for case in fixtures:
        for model in models:
            prompt = create_prompt(case)
            prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
            began = time.monotonic()
            try:
                response = call(model, prompt)
                report = parse_json_response(response['content'])
                record = {'case_id': case['case_id'], 'model': model, 'report': report,
                          'prompt_version': prompt_version, 'prompt_sha256': prompt_hash}
                _append(report_file, record)
                usage = response.get('usage') or {}
                _append(usage_file, {'case_id': case['case_id'], 'model': model,
                                     'prompt_version': prompt_version, 'prompt_sha256': prompt_hash,
                                     'input_tokens': usage.get('prompt_tokens'),
                                     'output_tokens': usage.get('completion_tokens'),
                                     'estimated_cost_usd': response.get('estimated_cost_usd'),
                                     'latency_seconds': round(time.monotonic() - began, 3)})
            except Exception as exc:
                # Avoid writing provider exception text: it may contain private request data.
                _append(error_file, {'case_id': case['case_id'], 'model': model,
                                     'error_type': type(exc).__name__,
                                     'latency_seconds': round(time.monotonic() - began, 3)})
    return report_file, usage_file, error_file


def _append(path, row):
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def litellm_call(model, prompt):
    import litellm
    reply = litellm.completion(
        model=model,
        messages=[{'role': 'user', 'content': prompt}],
        temperature=0,
        max_tokens=700,
        timeout=60,
        num_retries=0,
    )
    result = reply.choices[0].message.content
    usage = reply.usage
    token_counts = {
        'prompt_tokens': getattr(usage, 'prompt_tokens', None),
        'completion_tokens': getattr(usage, 'completion_tokens', None),
    }
    cost = None
    try:
        cost = litellm.completion_cost(completion_response=reply)
        if cost is not None:
            cost = float(cost)
    except Exception:
        pass
    return {'content': result, 'usage': token_counts, 'estimated_cost_usd': cost}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', default='benchmarks/fixtures/market_cases.json')
    parser.add_argument('--models', required=True, help='comma separated LiteLLM names')
    parser.add_argument('--output-dir', default='artifacts/live_benchmark')
    parser.add_argument('--max-calls', type=int, default=6)
    parser.add_argument('--confirm-live', action='store_true', help='Required for paid API calls')
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error('Live calls are disabled. Pass --confirm-live deliberately.')
    models = [x.strip() for x in args.models.split(',') if x.strip()]
    if not models or len(set(models)) != len(models):
        parser.error('Supply distinct nonempty model names')
    fixtures = json.loads(Path(args.fixtures).read_text(encoding='utf-8'))
    if not fixtures or len({x['case_id'] for x in fixtures}) != len(fixtures):
        parser.error('Fixtures must have unique case_id values')
    # Guard against inadvertent paid multi-model fan-out.
    reports, usages, errors = execute(fixtures, models, litellm_call, args.output_dir, args.max_calls)
    print(f'Completed. Reports: {reports}; usage: {usages}; errors: {errors}.')
    if errors.stat().st_size:
        raise SystemExit('Some model calls failed; inspect sanitized errors.jsonl')


if __name__ == '__main__':
    main()
