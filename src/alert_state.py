
import json
from pathlib import Path


class AlertState:
    """Track successfully sent stock alerts."""

    def __init__(self, file_path="alert_state.json"):
        self.file_path = Path(file_path)
        self.sent_alerts = self._load()

    def _load(self):
        if not self.file_path.exists():
            return set()

        with self.file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        return set(data.get("sent_alerts", []))

    def _key(self, stock_code, trading_date):
        return f"{stock_code.upper()}:{trading_date}"

    def was_sent(self, stock_code, trading_date):
        """Check whether an alert was already sent."""
        return self._key(stock_code, trading_date) in self.sent_alerts

    def mark_sent(self, stock_code, trading_date):
        """Record a successfully sent alert."""
        key = self._key(stock_code, trading_date)
        self.sent_alerts.add(key)

        self.file_path.parent.mkdir(
            parents=True, exist_ok=True
        )

        data = {
            "sent_alerts": sorted(self.sent_alerts)
        }

        temp_path = self.file_path.with_suffix(".tmp")

        with temp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        temp_path.replace(self.file_path)
