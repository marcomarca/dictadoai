from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dictado_ai.history import HistoryEntry, HistoryManager


class TestHistoryManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history_file = Path(self.temp_dir.name) / "logs" / "transcripts_history.jsonl"
        self.manager = HistoryManager(self.history_file)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_append_and_get_recent(self):
        entry1 = HistoryEntry(
            id="entry_1",
            timestamp="2026-09-06T18:00:00",
            text="Primer dictado de prueba",
            raw_asr="Primer dictado de prueba",
            word_count=4,
            duration_sec=2.0,
            wpm=120.0,
            paste_success=True,
            provider="GROQ",
        )
        entry2 = HistoryEntry(
            id="entry_2",
            timestamp="2026-09-06T18:01:00",
            text="Segundo dictado con corrección",
            raw_asr="Segundo dictado",
            word_count=4,
            duration_sec=3.0,
            wpm=80.0,
            paste_success=False,
            provider="WHISPER LOCAL",
        )

        self.manager.append_entry(entry1)
        self.manager.append_entry(entry2)

        recent = self.manager.get_recent(limit=10)
        self.assertEqual(len(recent), 2)
        # La más reciente debe estar primero (orden cronológico inverso)
        self.assertEqual(recent[0].id, "entry_2")
        self.assertEqual(recent[0].text, "Segundo dictado con corrección")
        self.assertFalse(recent[0].paste_success)

        self.assertEqual(recent[1].id, "entry_1")
        self.assertEqual(recent[1].text, "Primer dictado de prueba")
        self.assertTrue(recent[1].paste_success)

    def test_get_recent_limit(self):
        for i in range(10):
            entry = HistoryEntry(
                id=f"entry_{i}",
                timestamp="2026-09-06T18:00:00",
                text=f"Dictado {i}",
            )
            self.manager.append_entry(entry)

        recent = self.manager.get_recent(limit=3)
        self.assertEqual(len(recent), 3)
        self.assertEqual(recent[0].id, "entry_9")
        self.assertEqual(recent[1].id, "entry_8")
        self.assertEqual(recent[2].id, "entry_7")

    def test_get_recent_when_file_does_not_exist(self):
        fake_file = Path(self.temp_dir.name) / "nonexistent" / "history.jsonl"
        mgr = HistoryManager(fake_file)
        self.assertEqual(mgr.get_recent(), [])

    def test_clear_history(self):
        entry = HistoryEntry(id="e1", timestamp="t1", text="Texto")
        self.manager.append_entry(entry)
        self.assertTrue(self.history_file.exists())

        self.manager.clear()
        self.assertFalse(self.history_file.exists())
        self.assertEqual(self.manager.get_recent(), [])


if __name__ == "__main__":
    unittest.main()
