import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from dictado_ai.config import Settings
from dictado_ai.history import HistoryEntry, HistoryManager
from dictado_ai.gui.web_window import WebBridge


class TestWebBridgeAndHistory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history_file = Path(self.temp_dir.name) / "test_history.jsonl"
        self.history_mgr = HistoryManager(self.history_file)
        self.settings = Settings.default()

        self.mock_window = MagicMock()
        self.mock_toggle = MagicMock()
        self.mock_device = MagicMock()

        self.bridge = WebBridge(
            self.settings,
            self.history_mgr,
            self.mock_window,
            toggle_dictation_cb=self.mock_toggle,
            change_device_cb=self.mock_device,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_delete_entry_in_history_manager(self):
        e1 = HistoryEntry(id="entry-1", timestamp="2026-09-06T12:00:00Z", text="Texto 1")
        e2 = HistoryEntry(id="entry-2", timestamp="2026-09-06T12:05:00Z", text="Texto 2")
        self.history_mgr.append_entry(e1)
        self.history_mgr.append_entry(e2)

        self.assertEqual(len(self.history_mgr.get_recent(10)), 2)

        deleted = self.history_mgr.delete_entry("entry-1")
        self.assertTrue(deleted)

        remaining = self.history_mgr.get_recent(10)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].id, "entry-2")

        not_found = self.history_mgr.delete_entry("non-existent")
        self.assertFalse(not_found)

    def test_bridge_get_history_json(self):
        entry = HistoryEntry(
            id="e-abc",
            timestamp="2026-09-06T15:00:00Z",
            text="Prueba de dictado",
            word_count=3,
            wpm=120.0,
            paste_success=True,
        )
        self.history_mgr.append_entry(entry)

        res_json = self.bridge.getHistory(10)
        data = json.loads(res_json)
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "e-abc")
        self.assertEqual(data[0]["text"], "Prueba de dictado")

    def test_bridge_delete_history_item(self):
        entry = HistoryEntry(id="to-del", timestamp="2026-09-06T15:00:00Z", text="Eliminar")
        self.history_mgr.append_entry(entry)

        ok = self.bridge.deleteHistoryItem("to-del")
        self.assertTrue(ok)
        self.assertEqual(len(self.history_mgr.get_recent(10)), 0)

    def test_bridge_get_config(self):
        cfg_str = self.bridge.getConfig()
        cfg = json.loads(cfg_str)
        self.assertIn("auto_copy_clipboard", cfg)
        self.assertIn("hotkey", cfg)
        self.assertIn("provider", cfg)

    def test_bridge_save_config_setting(self):
        self.bridge.saveConfigSetting("cfgAutoCopy", True)
        self.assertTrue(self.settings.app.auto_copy_clipboard)

        self.bridge.saveConfigSetting("cfgAutoCopy", False)
        self.assertFalse(self.settings.app.auto_copy_clipboard)

    def test_bridge_toggle_dictation(self):
        self.bridge.toggleDictation()
        self.mock_toggle.assert_called_once()

    def test_bridge_set_audio_device(self):
        self.bridge.setAudioDevice("mic-1", "Micrófono USB")
        self.mock_device.assert_called_once_with("mic-1", "Micrófono USB")


if __name__ == "__main__":
    unittest.main()
