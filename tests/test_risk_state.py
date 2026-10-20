import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.alert_state import AlertState
from src.risk_alert import process_quotes, check_risk, send_discord


class RiskWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "sent.json"
        self.state = AlertState(self.path)
        self.quote = {"code": "NVDA", "date": "2026-10-20", "change_pct": -6.0}

    def test_risk_rule(self):
        self.assertIsNotNone(check_risk("NVDA", -6, 5))
        self.assertIsNone(check_risk("NVDA", -1, 5))

    def test_success_persists_and_deduplicates(self):
        with patch("src.risk_alert.send_discord") as send:
            result = process_quotes([self.quote], 5, True, self.state)
            self.assertEqual(result["sent"], 1)
            result = process_quotes([self.quote], 5, True, AlertState(self.path))
            self.assertEqual(result["duplicates"], 1)
            send.assert_called_once()

    def test_failed_send_does_not_mark_sent(self):
        with patch("src.risk_alert.send_discord", side_effect=RuntimeError("HTTP 500")):
            with self.assertRaises(RuntimeError):
                process_quotes([self.quote], 5, True, self.state)
        self.assertFalse(AlertState(self.path).was_sent("NVDA", "2026-10-20"))

    def test_dry_run_does_not_mark_sent(self):
        with patch("src.risk_alert.send_discord") as send:
            process_quotes([self.quote], 5, False, self.state)
            send.assert_not_called()
        self.assertFalse(self.state.was_sent("NVDA", "2026-10-20"))

    def test_next_date_can_alert(self):
        with patch("src.risk_alert.send_discord") as send:
            process_quotes([self.quote], 5, True, self.state)
            new_quote = {**self.quote, "date": "2026-10-21"}
            process_quotes([new_quote], 5, True, self.state)
            self.assertEqual(send.call_count, 2)

    def test_webhook_http_request(self):
        from unittest.mock import MagicMock
        response = MagicMock(status=204)
        with patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://example.org/test"}):
            with patch("src.risk_alert.urllib.request.urlopen") as open_url:
                open_url.return_value.__enter__.return_value = response
                send_discord("hello")
                self.assertEqual(open_url.call_args.args[0].get_method(), "POST")


if __name__ == "__main__":
    unittest.main()
