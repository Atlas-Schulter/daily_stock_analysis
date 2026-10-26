"""Live 20-case LLM Benchmark V2. Only runs after explicit --confirm-live."""
import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path
from benchmarks.evaluate_v2 import evaluate, load_jsonl
from src.llmops_pricing import estimate_cost 
from datetime import datetime, timezone

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
    """Decode strict JSON, with support for complete fenced JSON output."""
    if isinstance(text, list):
        text = ''.join(x.get('text', '') for x in text if isinstance(x, dict))
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Empty model content: possibly truncated by output token budget')
    text = text.strip()
    match = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', text, re.S | re.I)
    if match:
        text = match.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'Invalid model JSON: {exc.msg} at character {exc.pos}') from exc
    if not isinstance(data, dict):
        raise ValueError('LLM output must be a JSON object')
    return data


def is_quota_or_rate_limit(exc):
    """Detect throttling / quota failures without depending on LiteLLM imports."""
    message = str(exc).lower()
    return (
        type(exc).__name__ == 'RateLimitError'
        or '429' in message
        or 'resource_exhausted' in message
        or 'quota exceeded' in message
    )


def call_model(model, prompt):
    import litellm
    params = {}
    resolved = model
    if model.startswith('aihubmix/'):
        key = os.getenv('AIHUBMIX_API_KEY')
        if not key:
            raise ValueError('AIHUBMIX_API_KEY is missing')
        resolved = 'openai/' + model[len('aihubmix/'):]
        params.update(api_base='https://aihubmix.com/v1', api_key=key)

    # JSON mode is supported by Gemini's structured-output API; other providers
    # may require different parameters, so do not impose it universally.
    if resolved.startswith('gemini/'):
        params['response_format'] = {'type': 'json_object'}

    response = litellm.completion(
        model=resolved,
        messages=[
            {'role': 'system', 'content': SYSTEM_MESSAGE},
            {'role': 'user', 'content': prompt},
        ],
        temperature=0,
        max_tokens=4096,
        timeout=90,
        num_retries=0,
        stream=False,
        **params,
    )
    choice = response.choices[0]
    usage = getattr(response, 'usage', None)
    content = choice.message.content
    finish_reason = getattr(choice, 'finish_reason', None)
    print(
        f'[LLM Debug] model={model} finish_reason={finish_reason} '
        f'input_tokens={getattr(usage, "prompt_tokens", None)} '
        f'output_tokens={getattr(usage, "completion_tokens", None)} '
        f'content_length={len(content or "")}',
        flush=True,
    )
    # Keep the existing four-field caller contract for mock tests.
    return content, getattr(usage, 'prompt_tokens', None), getattr(usage, 'completion_tokens', None), None

def append_jsonl(path, item):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(item, ensure_ascii=False, default=str) + '\n')

def run(fixtures, models, max_calls, output_dir, caller=call_model, sample_limit=None):
    if max_calls < 1:
        raise ValueError('max_calls must be positive')
    cases = fixtures['cases']
    if sample_limit is not None:
        cases = cases[:sample_limit]
    planned = len(cases) * len(models)
    if planned > max_calls:
        raise ValueError(
            f'Plan has {planned} calls; --max-calls={max_calls}. '
            'Increase it explicitly or use --sample-limit.'
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_path = output_dir / 'reports.jsonl'
    usage_path = output_dir / 'usage.jsonl'
    errors_path = output_dir / 'errors.jsonl'
    for file in (reports_path, usage_path, errors_path):
        file.write_text('', encoding='utf-8')

    attempted = 0
    succeeded = 0
    failures = 0
    skipped = 0
    for model in models:
        for index, case in enumerate(cases):
            prompt = make_prompt(case)
            digest = hashlib.sha256(
                (SYSTEM_MESSAGE + '\n' + prompt).encode('utf-8')
            ).hexdigest()
            started_at = datetime.now(timezone.utc)
            start = time.monotonic()
            attempted += 1
            try:
                content, in_tokens, out_tokens, caller_cost = caller(model, prompt)
                latency = round(time.monotonic() - start, 3)

                # A completed API call is billable even when its JSON is invalid.
                try:
                    pricing = estimate_cost(
                        model,
                        {'prompt_tokens': in_tokens, 'completion_tokens': out_tokens},
                        timestamp=started_at,
                    )
                except Exception as pricing_exc:
                    print(f'[Pricing] unavailable for {model}: {type(pricing_exc).__name__}', flush=True)
                    pricing = {
                        'estimated_cost_usd': None,
                        'pricing_status': 'unpriced',
                        'pricing_tier': None,
                        'pricing_source': None,
                        'pricing_rates_per_million': None,
                    }
                if caller_cost is not None:
                    pricing['estimated_cost_usd'] = caller_cost
                    pricing['pricing_status'] = 'caller_reported'

                usage_row = {
                    'case_id': case['case_id'],
                    'model': model,
                    'prompt_version': PROMPT_VERSION,
                    'prompt_sha256': digest,
                    'input_tokens': in_tokens,
                    'output_tokens': out_tokens,
                    'estimated_cost_usd': pricing['estimated_cost_usd'],
                    'latency_seconds': latency,
                    'pricing_status': pricing['pricing_status'],
                    'pricing_tier': pricing['pricing_tier'],
                    'pricing_source': pricing['pricing_source'],
                    'pricing_rates_per_million': pricing['pricing_rates_per_million'],
                }
                append_jsonl(usage_path, usage_row)

                try:
                    report = decode_report(content)
                except (ValueError, TypeError) as parse_exc:
                    # Never log raw model content, which may contain sensitive data.
                    raise ValueError(
                        f'{parse_exc}; response_length={len(content or "")}'
                    ) from parse_exc

                append_jsonl(reports_path, {
                    'case_id': case['case_id'], 'model': model,
                    'report': report, 'prompt_version': PROMPT_VERSION,
                    'prompt_sha256': digest,
                })
                succeeded += 1
                print(f'OK {model} {case["case_id"]} {latency}s', flush=True)
            except Exception as exc:
                failures += 1
                rate_limited = is_quota_or_rate_limit(exc)
                append_jsonl(errors_path, {
                    'case_id': case['case_id'], 'model': model,
                    'error_type': type(exc).__name__,
                    'error_message': str(exc)[:300],
                })
                print(f'ERROR {model} {case["case_id"]}: {type(exc).__name__}', flush=True)
                if rate_limited:
                    # Fail closed for the current provider/model; don't burn
                    # remaining calls once quotas or rate limits are hit.
                    remaining = cases[index + 1:]
                    for unattempted in remaining:
                        append_jsonl(errors_path, {
                            'case_id': unattempted['case_id'], 'model': model,
                            'error_type': 'SkippedAfterRateLimit',
                            'error_message': 'Not requested after previous 429',
                        })
                    skipped += len(remaining)
                    print(f'[Rate limit] stopping {model}; skipped {len(remaining)} cases', flush=True)
                    break
            # Reduce throttling risk; configurable by environment variable.
            delay = float(os.getenv('LLM_BENCHMARK_DELAY_SECONDS', '2'))
            if delay > 0 and index + 1 < len(cases):
                time.sleep(delay)

    results = evaluate(fixtures, load_jsonl(reports_path), load_jsonl(usage_path))
    results['planned_calls'] = planned
    results['attempted_calls'] = attempted
    results['failed_calls'] = failures
    results['skipped_calls'] = skipped
    results['successful_calls'] = succeeded
    results['call_success_rate'] = round(succeeded / attempted, 4) if attempted else None
    output = output_dir / 'benchmark_comparison.json'
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({
        'by_model': results['by_model'],
        'attempted_calls': attempted,
        'skipped_calls': skipped,
        'call_success_rate': results['call_success_rate'],
    }, indent=2))
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixtures', default='benchmarks/fixtures/market_cases_v2.json')
    parser.add_argument('--models', required=True, help='Comma-separated model names')
    parser.add_argument('--max-calls', type=int, default=6)
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
