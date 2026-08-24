"""Mock-provider smoke tests for the pipeline."""
from __future__ import annotations
import os
import tempfile
import unittest

from app.pipeline import fetch_and_run


class TestMockPipeline(unittest.TestCase):
    def test_fetch_and_run_importable(self):
        """Regression test: fetch_and_run must be importable from app.pipeline."""
        from app.pipeline import fetch_and_run
        self.assertTrue(callable(fetch_and_run))

    def test_mock_run_produces_generations(self):
        """End-to-end mock run: should produce generations at zero cost."""
        os.environ["GENERATOR_PROVIDER"] = "mock"
        os.environ["JUDGE_PROVIDER"] = "mock"
        db_path = os.path.join(tempfile.gettempdir(), "midya_mock_test.db")
        if os.path.exists(db_path):
            os.remove(db_path)
        stats = fetch_and_run(query="test", timeframe="24h", db_url=f"sqlite:///{db_path}")
        self.assertGreater(stats["generated"], 0, "Mock run should produce at least one generation")
        self.assertEqual(stats["cost_usd"], 0.0, "Mock run should have zero cost")
        self.assertEqual(stats["embedder_mode"], "jaccard", "Mock run should use jaccard fallback")


if __name__ == "__main__":
    unittest.main()