
import unittest
from src.risk_alert import check_risk


class TestRiskAlert(unittest.TestCase):

    def test_large_drop(self):
        result = check_risk("NVDA", -5.8, 5)
        self.assertIn("Stock Risk Alert", result)

    def test_small_drop(self):
        result = check_risk("AAPL", -2, 5)
        self.assertIsNone(result)

    def test_exact_threshold(self):
        result = check_risk("TSLA", -5, 5)
        self.assertIsNotNone(result)

    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):
            check_risk("NVDA", -5, -1)


if __name__ == "__main__":
    unittest.main()
