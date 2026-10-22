"""Best-effort LLM usage telemetry and deterministic report checks (stdlib only)."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def record_usage(usage, model, call_type, stock_code=None, output=None, prices=None):
    """Append one model response's reported usage. Pricing is optional and explicit.

    prices: {model: {'input_per_million': 0.5, 'output_per_million': 2.0}}
    Never log prompts, raw model responses, API keys or webhook URLs.
    """
    usage = usage or {}
    input_tokens = max(0, int(usage.get('prompt_tokens') or 0))
    output_tokens = max(0, int(usage.get('completion_tokens') or 0))
    model = str(model or 'unknown')
    price = (prices or {}).get(model)
    if price is not None:
        in_price = float(price['input_per_million'])
        out_price = float(price['output_per_million'])
        if min(in_price, out_price) < 0:
            raise ValueError('Token prices must be non-negative')
        estimated_cost = round((input_tokens * in_price + output_tokens * out_price) / 1_000_000, 8)
    else:
        estimated_cost = None
    record = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event': 'llm_usage', 'model': model, 'call_type': str(call_type),
        'stock_code': stock_code, 'input_tokens': input_tokens,
        'output_tokens': output_tokens, 'total_tokens': input_tokens + output_tokens,
        'estimated_cost_usd': estimated_cost,
        'pricing_status': 'priced' if price is not None else 'unpriced',
    }
    path = Path(output or os.getenv('LLMOPS_USAGE_FILE', 'artifacts/llm_usage.jsonl'))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    return record


def summarize_usage(path='artifacts/llm_usage.jsonl', prices=None):
    """Summarize already-recorded rows; no API calls and no retroactive repricing."""
    items = []
    source = Path(path)
    if source.exists():
        for line in source.read_text(encoding='utf-8').splitlines():
            if line.strip():
                items.append(json.loads(line))
    models = {}
    for item in items:
        model = item['model']
        row = models.setdefault(model, {'calls': 0, 'input_tokens': 0,
                                        'output_tokens': 0, 'estimated_cost_usd': 0.0,
                                        'unpriced_calls': 0})
        row['calls'] += 1
        row['input_tokens'] += item['input_tokens']
        row['output_tokens'] += item['output_tokens']
        if item['estimated_cost_usd'] is None:
            row['unpriced_calls'] += 1
        else:
            row['estimated_cost_usd'] += item['estimated_cost_usd']
    for row in models.values():
        row['estimated_cost_usd'] = round(row['estimated_cost_usd'], 8)
    return {'calls': len(items), 'by_model': models,
            'cost_complete': all(i['estimated_cost_usd'] is not None for i in items)}


def evaluate_report(report):
    """Structural evaluation; does NOT assert trading advice or market facts are correct."""
    if not isinstance(report, dict):
        return {'passed': False, 'missing_fields': ['report:not_an_object']}
    required = ['analysis_summary', 'operation_advice', 'sentiment_score']
    missing = [key for key in required if report.get(key) is None or report.get(key) == '']
    dashboard = report.get('dashboard') or {}
    if not isinstance(dashboard, dict):
        dashboard = {}
    core = dashboard.get('core_conclusion') or {}
    if not isinstance(core, dict) or not str(core.get('one_sentence') or '').strip():
        missing.append('dashboard.core_conclusion.one_sentence')
    sentiment = report.get('sentiment_score')
    if sentiment is not None:
        try:
            if not 0 <= float(sentiment) <= 100:
                missing.append('sentiment_score:out_of_range')
        except (TypeError, ValueError):
            missing.append('sentiment_score:not_numeric')
    return {'passed': not missing, 'missing_fields': missing}


def record_evaluation(report, model='unknown', stock_code=None,
                      output='artifacts/llm_evaluations.jsonl'):
    """Persist only quality scores/missing-field names, not model output text."""
    result = evaluate_report(report)
    record = {'timestamp': datetime.now(timezone.utc).isoformat(),
              'event': 'llm_report_evaluation', 'model': str(model),
              'stock_code': stock_code, **result}
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    return record
