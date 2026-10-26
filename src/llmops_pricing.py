"""Shared, explicit LLM token-cost estimates for production and benchmarks.

Pricing is deliberately local and auditable. It is not a billing API and must
not be presented as the provider's final invoice. No network calls are made.
"""

import json
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

_DEFAULT_CATALOG = Path(__file__).resolve().parents[1] / "config" / "llm_pricing.json"
_USD_8DP = Decimal("0.00000001")


def load_pricing_catalog(path=None):
    """Load model prices; allow a custom local config via LLMOPS_PRICING_FILE."""
    source = Path(path or os.environ.get("LLMOPS_PRICING_FILE") or _DEFAULT_CATALOG)
    if not source.is_file():
        return {}
    data = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("models"), dict):
        raise ValueError("Pricing config must contain an object named 'models'")
    return data["models"]


def _inside_utc_window(now, start, end):
    """Check a UTC clock window, including windows that cross midnight."""
    hhmm = now.astimezone(timezone.utc).strftime("%H:%M")
    return start <= hhmm < end if start <= end else (hhmm >= start or hhmm < end)


def _get_cached_tokens(usage):
    """Read the standard OpenAI-compatible cached input count, if supplied."""
    details = usage.get("prompt_tokens_details") or {}
    if not isinstance(details, dict):
        details = {"cached_tokens": getattr(details, "cached_tokens", None)}
    cached = details.get("cached_tokens")
    return int(cached) if cached is not None else None


def _base_result(status, model):
    return {
        "model": str(model or "unknown"),
        "estimated_cost_usd": None,
        "pricing_status": status,
        "pricing_tier": None,
        "pricing_source": None,
        "pricing_rates_per_million": None,
        "cached_input_tokens": None,
    }


def estimate_cost(model, usage, *, prices=None, timestamp=None):
    """Estimate USD for one completed call using reported tokens and explicit rates.

    Args:
        model: Exact routed model ID, e.g. ``aihubmix/deepseek-v4.1-flash``.
        usage: Dictionary containing prompt_tokens and completion_tokens.
        prices: Optional legacy per-model price mapping; overrides the catalog.
        timestamp: A timezone-aware datetime representing the API call time.

    Returns:
        Pricing metadata with estimated_cost_usd=None when the rate or token
        data is missing. Never treats missing usage as a free API call.
    """
    model = str(model or "unknown")
    result = _base_result("unpriced", model)
    catalog = prices if prices is not None else load_pricing_catalog()
    config = catalog.get(model)
    if config is None:
        return result

    result["pricing_source"] = config.get("source", "manual_override")
    rate_type = config.get("type", "fixed")
    now = timestamp or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Pricing timestamp must be timezone-aware")

    if rate_type == "utc_peak_offpeak":
        peak = any(_inside_utc_window(now, start, end)
                   for start, end in config["peak_windows_utc"])
        tier = "peak" if peak else "offpeak"
        rates = config["tiers"][tier]
    elif rate_type == "env_tier":
        key = config["selector_env"]
        tier = os.environ.get(key, "").strip().lower()
        if tier not in config["tiers"]:
            result["pricing_status"] = "tier_unselected"
            return result
        rates = config["tiers"][tier]
    elif rate_type == "fixed":
        tier = "fixed"
        rates = config
    else:
        raise ValueError(f"Unsupported pricing type: {rate_type}")

    result["pricing_tier"] = tier
    result["pricing_rates_per_million"] = {
        name: rates[name] for name in
        ("input_per_million", "output_per_million", "cached_input_per_million")
        if name in rates
    }
    usage = usage or {}
    if usage.get("prompt_tokens") is None or usage.get("completion_tokens") is None:
        result["pricing_status"] = "usage_missing"
        return result
    try:
        input_tokens = int(usage["prompt_tokens"])
        output_tokens = int(usage["completion_tokens"])
        cached = _get_cached_tokens(usage)
        in_rate = Decimal(str(rates["input_per_million"]))
        out_rate = Decimal(str(rates["output_per_million"]))
        cache_rate = Decimal(str(rates.get("cached_input_per_million", rates["input_per_million"])))
        if min(input_tokens, output_tokens) < 0 or (cached is not None and (cached < 0 or cached > input_tokens)):
            raise ValueError("Token counts must be non-negative; cached tokens <= input tokens")
        if min(in_rate, out_rate, cache_rate) < 0:
            raise ValueError("Token prices must be non-negative")
    except (ValueError, TypeError, InvalidOperation, KeyError) as exc:
        raise ValueError(f"Invalid pricing input for {model}: {exc}") from exc

    # Assume no discounted cache reads if the provider did not supply a count.
    billed_cached = cached if cached is not None else 0
    cost = ((Decimal(input_tokens - billed_cached) * in_rate)
            + (Decimal(billed_cached) * cache_rate)
            + (Decimal(output_tokens) * out_rate)) / Decimal(1_000_000)
    result["estimated_cost_usd"] = float(cost.quantize(_USD_8DP, rounding=ROUND_HALF_UP))
    result["cached_input_tokens"] = cached
    result["pricing_status"] = "estimated"
    return result
