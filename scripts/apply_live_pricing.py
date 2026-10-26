"""Safely add shared pricing to an existing benchmark Live V2 runner.

This script edits only known cost-related fragments. It refuses unknown layouts,
so user-specific changes such as max_tokens, case filters and debug logs survive.
Run from the repository root: python scripts/apply_live_pricing.py
"""

from pathlib import Path

TARGET = Path('benchmarks/live_v2.py')


def _replace_once(source, before, after, name):
    if source.count(before) != 1:
        raise ValueError(f'{name}: expected exactly one original fragment; file left unchanged')
    return source.replace(before, after, 1)


def main():
    if not TARGET.is_file():
        raise SystemExit(f'Missing {TARGET}; run from repository root')
    original = TARGET.read_text(encoding='utf-8')
    if "'pricing_status':pricing['pricing_status']" in original:
        print('Shared pricing appears already integrated; no changes made')
        return
    text = original
    text = _replace_once(
        text,
        'from pathlib import Path\n',
        'from pathlib import Path\nfrom datetime import datetime, timezone\n'
        'from src.llmops_pricing import estimate_cost\n',
        'pricing imports',
    )
    text = _replace_once(
        text,
        """    cost = None
    if not model.startswith('aihubmix/'):
        try:
            candidate = litellm.completion_cost(completion_response=response)
            if candidate is not None: cost = float(candidate)
        except Exception: pass
    return response.choices[0].message.content, input_tokens, output_tokens, cost""",
        """    # Let the shared estimator price every provider using one rate catalog.
    # Preserve the four-value signature required by existing mock callers.
    return response.choices[0].message.content, input_tokens, output_tokens, None""",
        'legacy model-specific pricing',
    )
    text = _replace_once(
        text,
        """            start = time.monotonic()
            try:
                content, in_tokens, out_tokens, cost = caller(model, prompt)
                latency = round(time.monotonic() - start, 3)
                report = decode_report(content)""",
        """            started_at = datetime.now(timezone.utc)
            start = time.monotonic()
            try:
                content, in_tokens, out_tokens, cost = caller(model, prompt)
                latency = round(time.monotonic() - start, 3)
                # Use API start time for UTC peak/off-peak pricing.
                pricing = estimate_cost(
                    model,
                    {'prompt_tokens': in_tokens, 'completion_tokens': out_tokens},
                    timestamp=started_at,
                )
                # Retain explicitly supplied costs from custom or mock callers.
                if cost is not None:
                    pricing['estimated_cost_usd'] = cost
                    pricing['pricing_status'] = 'caller_reported'
                cost = pricing['estimated_cost_usd']
                report = decode_report(content)""",
        'shared cost estimation',
    )
    text = _replace_once(
        text,
        "'estimated_cost_usd':cost,'latency_seconds':latency})",
        """'estimated_cost_usd':cost,'latency_seconds':latency,
                             'pricing_status':pricing['pricing_status'],
                             'pricing_tier':pricing['pricing_tier'],
                             'pricing_source':pricing['pricing_source'],
                             'pricing_rates_per_million':pricing['pricing_rates_per_million']})""",
        'usage report metadata',
    )
    # Only persist if every expected fragment was found and transformed.
    TARGET.write_text(text, encoding='utf-8')
    print(f'Updated {TARGET} with shared pricing; existing call/debug settings preserved')


if __name__ == '__main__':
    main()
