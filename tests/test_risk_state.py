
import tempfile
import unittest
from pathlib import Path

from src.alert_state import AlertState


class TestAlertState(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_file = (
            Path(self.temp_dir.name) / "alert_state.json"
        )
        self.state = AlertState(self.state_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_new_alert(self):
        self.assertFalse(
            self.state.was_sent("NVDA", "2026-10-20")
        )

    def test_duplicate_alert(self):
        self.state.mark_sent("NVDA", "2026-10-20")

        self.assertTrue(
            self.state.was_sent("NVDA", "2026-10-20")
        )

    def test_different_date(self):
        self.state.mark_sent("NVDA", "2026-10-20")

        self.assertFalse(
            self.state.was_sent("NVDA", "2026-10-21")
        )

    def test_different_stock(self):
        self.state.mark_sent("NVDA", "2026-10-20")

        self.assertFalse(
            self.state.was_sent("AAPL", "2026-10-20")
        )

    def test_persistence(self):
        self.state.mark_sent("NVDA", "2026-10-20")

        restored = AlertState(self.state_file)

        self.assertTrue(
            restored.was_sent("NVDA", "2026-10-20")
        )


if __name__ == "__main__":
    unittest.main()
