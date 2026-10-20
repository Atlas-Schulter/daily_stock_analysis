
import os
import unittest
from unittest.mock import patch, MagicMock

from src.risk_alert import (
    check_risk_from_quote,
    send_discord
)


class TestRiskIntegration(unittest.TestCase):

    @patch("src.risk_alert.urllib.request.urlopen")
    def test_risk_alert_to_discord(self, mock_urlopen):
        """Verify risk detection and Discord request."""

        # Simulated market data
        quote = {
            "code": "NVDA",
            "change_pct": -6.0
        }

        alert = check_risk_from_quote(
            quote,
            threshold=5.0
        )

        self.assertIsNotNone(alert)
        self.assertIn("NVDA", alert)
        self.assertIn("-6.00%", alert)

        # Mock Discord HTTP response
        mock_response = MagicMock()
        mock_response.status = 204
        mock_urlopen.return_value.__enter__.return_value = (
            mock_response
        )

        with patch.dict(
            os.environ,
            {"DISCORD_WEBHOOK_URL": "https://example.com/webhook"}
        ):
            send_discord(alert)

        mock_urlopen.assert_called_once()

        request = mock_urlopen.call_args.args[0]

        self.assertEqual(
            request.get_method(),
            "POST"
        )

        self.assertIn(
            b"NVDA",
            request.data
        )

    @patch("src.risk_alert.urllib.request.urlopen")
    def test_no_alert_no_discord(self, mock_urlopen):
        """Verify normal price changes do not trigger alerts."""

        quote = {
            "code": "AAPL",
            "change_pct": -1.0
        }

        alert = check_risk_from_quote(quote, 5.0)

        self.assertIsNone(alert)

        if alert:
            send_discord(alert)

        mock_urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
