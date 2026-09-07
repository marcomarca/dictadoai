import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dictado_ai.history import HistoryEntry, HistoryManager


class TestHistoryWeeklyMetrics(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history_file = Path(self.temp_dir.name) / "test_history.jsonl"
        self.manager = HistoryManager(self.history_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_metrics_empty_history(self):
        metrics = self.manager.get_weekly_metrics()
        self.assertEqual(metrics["avg_wpm"], 0)
        self.assertEqual(metrics["total_words"], 0)
        self.assertEqual(metrics["total_dictations"], 0)
        self.assertEqual(metrics["minutes_saved"], 0.0)

    def test_metrics_with_recent_and_old_entries(self):
        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(days=2)).isoformat()
        old_ts = (now - timedelta(days=20)).isoformat()

        # Entrada reciente: 40 palabras, 120 WPM, duración 10s
        e_recent = HistoryEntry(
            id="e-recent",
            timestamp=recent_ts,
            text="Esta es una prueba reciente de dictado",
            word_count=40,
            duration_sec=10.0,
            wpm=120.0,
        )

        # Entrada antigua (hace 20 días): 100 palabras, 150 WPM (no debe contar en weekly)
        e_old = HistoryEntry(
            id="e-old",
            timestamp=old_ts,
            text="Entrada muy vieja",
            word_count=100,
            duration_sec=30.0,
            wpm=150.0,
        )

        self.manager.append_entry(e_recent)
        self.manager.append_entry(e_old)

        metrics = self.manager.get_weekly_metrics()
        self.assertEqual(metrics["total_dictations"], 1)
        self.assertEqual(metrics["total_words"], 40)
        self.assertEqual(metrics["avg_wpm"], 120)

        # 40 palabras a 40 WPM manual = 60 seg. Duró 10s hablando. Ahorro = 50s = ~0.8 min.
        self.assertGreater(metrics["minutes_saved"], 0.0)


if __name__ == "__main__":
    unittest.main()
