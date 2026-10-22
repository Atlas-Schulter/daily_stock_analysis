import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.observability import RunMetrics, emit


class TestObservability(unittest.TestCase):
    def test_metrics_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metrics.json"
            metrics = RunMetrics()
            metrics.data["stocks_checked"] = 3
            metrics.finish("success", path)
            output = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(output["stocks_checked"], 3)
            self.assertEqual(output["llm_calls"], 0)
            self.assertEqual(output["status"], "success")

    def test_llm_usage_estimate(self):
        metrics = RunMetrics()
        metrics.llm_usage(1000, 2000, 1.0, 2.0)
        self.assertEqual(metrics.data["llm_cost_usd"], 0.005)
        self.assertEqual(metrics.data["llm_calls"], 1)

    def test_structured_log(self):
        with patch("builtins.print") as printer:
            emit("example", stocks_checked=2)
            record = json.loads(printer.call_args.args[0])
            self.assertEqual(record["event"], "example")
            self.assertEqual(record["stocks_checked"], 2)


if __name__ == "__main__":
    unittest.main()
