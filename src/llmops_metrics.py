"""Best-effort LLM usage telemetry and deterministic report checks (stdlib only)."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from src.llmops_pricing import estimate_cost


def record_usage(usage, model, call_type, stock_code=None, output=None, prices=None):
    """Append one model's usage and estimated cost without storing raw content.

    The prices argument remains supported for manual per-model rate overrides.
    If omitted, src.llmops_pricing loads config/llm_pricing.json.
    Missing token usage remains explicitly flagged rather than treated as free.
    """
    usage = usage or {}
    input_reported = usage.get('prompt_tokens') is not None
    output_reported = usage.get('completion_tokens') is not None
    input_tokens = max(0, int(usage.get('prompt_tokens') or 0))
    output_tokens = max(0, int(usage.get('completion_tokens') or 0))
    model = str(model or 'unknown')
    now = datetime.now(timezone.utc)

    pricing = estimate_cost(model, usage, prices=prices, timestamp=now)
    record = {
        'timestamp': now.isoformat(),
        'event': 'llm_usage',
        'model': model,
        'call_type': str(call_type),
        'stock_code': stock_code,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'total_tokens': input_tokens + output_tokens,
        'usage_status': 'reported' if input_reported and output_reported else 'missing',
        'estimated_cost_usd': pricing['estimated_cost_usd'],
        'pricing_status': pricing['pricing_status'],
        'pricing_tier': pricing['pricing_tier'],
        'pricing_source': pricing['pricing_source'],
        'pricing_rates_per_million': pricing['pricing_rates_per_million'],
        'cached_input_tokens': pricing['cached_input_tokens'],
    }
    path = Path(output or os.getenv('LLMOPS_USAGE_FILE', 'artifacts/llm_usage.jsonl'))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    return record


def summarize_usage(path='artifacts/llm_usage.jsonl', prices=None):
    """Aggregate stored usage; never reprice historic rows or invoke an API."""
    items = []
    source = Path(path)
    if source.exists():
        for line in source.read_text(encoding='utf-8').splitlines():
            if line.strip():
                items.append(json.loads(line))
    models = {}
    for item in items:
        model = item['model']
        row = models.setdefault(model, {
            'calls': 0,
            'input_tokens': 0,
            'output_tokens': 0,
            'estimated_cost_usd': 0.0,
            'known_cost_usd': 0.0,
            'unpriced_calls': 0,
        })
        row['calls'] += 1
        row['input_tokens'] += item['input_tokens'] or 0
        row['output_tokens'] += item['output_tokens'] or 0
        if item.get('estimated_cost_usd') is None:
            row['unpriced_calls'] += 1
        else:
            row['known_cost_usd'] += item['estimated_cost_usd']
    for row in models.values():
        row['known_cost_usd'] = round(row['known_cost_usd'], 8)
        # A partial sum must never be mistaken for the full API bill.
        row['estimated_cost_usd'] = (
            row['known_cost_usd'] if row['unpriced_calls'] == 0 else None
        )
    return {
        'calls': len(items),
        'by_model': models,
        'cost_complete': all(i.get('estimated_cost_usd') is not None for i in items),
    }


def evaluate_report(report):
    """Structural evaluation; does NOT assert trading or market facts are correct."""
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
    """Persist only quality scores and missing-field names, never model text."""
    result = evaluate_report(report)
    record = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'event': 'llm_report_evaluation',
        'model': str(model),
        'stock_code': stock_code,
        **result,
    }
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')
    return record
