"""Offline tests for the shared LLM pricing and telemetry functions."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from src.llmops_metrics import record_usage, summarize_usage
from src.llmops_pricing import estimate_cost


class PricingTests(unittest.TestCase):
    MODEL = "aihubmix/deepseek-v4.1-flash"
    TOKENS = {"prompt_tokens": 1000000, "completion_tokens": 1000000}

    def test_deepseek_offpeak_rate(self):
        now = datetime(2026, 10, 23, 12, 30, tzinfo=timezone.utc)
        cost = estimate_cost(self.MODEL, self.TOKENS, timestamp=now)
        self.assertEqual(cost["pricing_tier"], "offpeak")
        self.assertEqual(cost["estimated_cost_usd"], 0.775)
        self.assertEqual(cost["pricing_status"], "estimated")

    def test_deepseek_peak_rate(self):
        now = datetime(2026, 10, 23, 7, 30, tzinfo=timezone.utc)
        cost = estimate_cost(self.MODEL, self.TOKENS, timestamp=now)
        self.assertEqual(cost["pricing_tier"], "peak")
        self.assertEqual(cost["estimated_cost_usd"], 1.549)

    def test_peak_window_boundaries(self):
        for hour, minute, expected in [(0, 59, "offpeak"), (1, 0, "peak"),
                                       (4, 0, "offpeak"), (6, 0, "peak"),
                                       (10, 0, "offpeak")]:
            with self.subTest(hour=hour, minute=minute):
                now = datetime(2026, 10, 23, hour, minute, tzinfo=timezone.utc)
                self.assertEqual(estimate_cost(self.MODEL, self.TOKENS, timestamp=now)["pricing_tier"], expected)

    def test_cached_input_rate(self):
        usage = {
            "prompt_tokens": 1000000,
            "completion_tokens": 1000000,
            "prompt_tokens_details": {"cached_tokens": 500000},
        }
        now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
        cost = estimate_cost(self.MODEL, usage, timestamp=now)
        self.assertEqual(cost["cached_input_tokens"], 500000)
        self.assertEqual(cost["estimated_cost_usd"], 0.69905)

    def test_missing_usage_is_not_free(self):
        now = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
        cost = estimate_cost(self.MODEL, {"prompt_tokens": 100}, timestamp=now)
        self.assertEqual(cost["pricing_status"], "usage_missing")
        self.assertIsNone(cost["estimated_cost_usd"])

    def test_gemini_billing_tier_must_be_explicit(self):
        with patch.dict(os.environ, {}, clear=True):
            cost = estimate_cost("gemini/gemini-2.5-flash", self.TOKENS)
            self.assertEqual(cost["pricing_status"], "tier_unselected")
            self.assertIsNone(cost["estimated_cost_usd"])
        with patch.dict(os.environ, {"LLMOPS_GEMINI_BILLING_TIER": "free"}):
            cost = estimate_cost("gemini/gemini-2.5-flash", self.TOKENS)
            self.assertEqual(cost["estimated_cost_usd"], 0.0)
            self.assertEqual(cost["pricing_tier"], "free")
        with patch.dict(os.environ, {"LLMOPS_GEMINI_BILLING_TIER": "paid"}):
            cost = estimate_cost("gemini/gemini-2.5-flash", self.TOKENS)
            self.assertEqual(cost["estimated_cost_usd"], 2.8)

    def test_other_models_remain_unpriced(self):
        self.assertEqual(estimate_cost("unknown-model", self.TOKENS)["pricing_status"], "unpriced")

    def test_legacy_explicit_price_override(self):
        prices = {"my-model": {"input_per_million": 0.5, "output_per_million": 2}}
        cost = estimate_cost("my-model", {"prompt_tokens": 1000, "completion_tokens": 500}, prices=prices)
        self.assertEqual(cost["estimated_cost_usd"], 0.0015)

    def test_record_and_summary_do_not_reprice_missing_calls(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "usage.jsonl"
            record = record_usage({"prompt_tokens": 1000, "completion_tokens": 500},
                                  self.MODEL, "analysis", output=file)
            self.assertEqual(record["usage_status"], "reported")
            self.assertEqual(record["pricing_status"], "estimated")
            missing = record_usage({}, self.MODEL, "analysis", output=file)
            self.assertEqual(missing["usage_status"], "missing")
            self.assertIsNone(missing["estimated_cost_usd"])
            summary = summarize_usage(file)
            row = summary["by_model"][self.MODEL]
            self.assertEqual(row["calls"], 2)
            self.assertEqual(row["unpriced_calls"], 1)
            self.assertIsNone(row["estimated_cost_usd"])
            self.assertIsNotNone(row["known_cost_usd"])
            self.assertFalse(summary["cost_complete"])
            self.assertEqual(len(file.read_text(encoding="utf-8").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
