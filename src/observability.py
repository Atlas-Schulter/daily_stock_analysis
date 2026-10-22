"""Structured stdout logging and JSON run metrics, stdlib only."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


def emit(event, level="INFO", **fields):
    record = {"timestamp": datetime.now(timezone.utc).isoformat(),
              "level": level, "event": event, **fields}
    print(json.dumps(record, ensure_ascii=False, default=str), flush=True)


class RunMetrics:
    def __init__(self, workflow="stock-risk-alert"):
        self.started = time.monotonic()
        self.data = {"workflow": workflow, "status": "running", "stocks_checked": 0,
                     "market_data_errors": 0, "alerts_detected": 0,
                     "alerts_sent": 0, "duplicates_skipped": 0,
                     "llm_calls": 0, "input_tokens": 0, "output_tokens": 0,
                     "llm_cost_usd": 0.0}

    def llm_usage(self, input_tokens, output_tokens, input_per_million_usd, output_per_million_usd):
        """Call explicitly after a real LLM response with actual usage and known pricing."""
        if min(input_tokens, output_tokens, input_per_million_usd, output_per_million_usd) < 0:
            raise ValueError("Usage and pricing must be nonnegative")
        cost = (input_tokens * input_per_million_usd +
                output_tokens * output_per_million_usd) / 1_000_000
        self.data["llm_calls"] += 1
        self.data["input_tokens"] += input_tokens
        self.data["output_tokens"] += output_tokens
        self.data["llm_cost_usd"] = round(self.data["llm_cost_usd"] + cost, 8)
        emit("llm_usage", input_tokens=input_tokens, output_tokens=output_tokens,
             estimated_cost_usd=round(cost, 8))

    def finish(self, status, output="artifacts/risk_metrics.json"):
        self.data["status"] = status
        self.data["duration_seconds"] = round(time.monotonic() - self.started, 3)
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        emit("run_complete", **self.data)
        return path


def notify_failure():
    """Workflow's isolated failure job; no webhook URLs are logged."""
    import urllib.request
    webhook = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook:
        emit("failure_notification_skipped", level="WARNING", reason="missing_webhook")
        return
    repo = os.getenv("GITHUB_REPOSITORY", "unknown")
    run_id = os.getenv("GITHUB_RUN_ID", "unknown")
    link = f"https://github.com/{repo}/actions/runs/{run_id}"
    payload = json.dumps({"content": f"❌ Stock Risk Alert workflow failed\n{link}"}).encode()
    request = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status not in (200, 204):
            raise RuntimeError(f"Discord returned HTTP {response.status}")
    emit("failure_notification_sent")


if __name__ == "__main__":
    notify_failure()
