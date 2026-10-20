"""Small JSON-backed alert history for GitHub Actions cache."""
import json
from pathlib import Path


class AlertState:
    def __init__(self, path=".state/alert_state.json"):
        self.path = Path(path)
        self.sent = self._load()

    def _load(self):
        if not self.path.exists():
            return set()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("sent_alerts"), list):
            raise ValueError("Invalid alert state format")
        return set(data["sent_alerts"])

    @staticmethod
    def key(symbol, market_date):
        return f"{symbol.upper()}:{market_date}"

    def was_sent(self, symbol, market_date):
        return self.key(symbol, market_date) in self.sent

    def mark_sent(self, symbol, market_date):
        self.sent.add(self.key(symbol, market_date))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"sent_alerts": sorted(self.sent)}, indent=2), encoding="utf-8")
        tmp.replace(self.path)
