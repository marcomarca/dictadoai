import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from dictado_ai.config import Settings, PathsConfig, AppConfig, RecordingWindowStyle
from dictado_ai.gui.overlay import DictationOverlay
from dictado_ai.gui.web_window import WebBridge
from dictado_ai.history import HistoryManager


class TestOverlayAndRecordingWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        paths = PathsConfig(project_root=self.temp_path, user_data_dir=self.temp_path)
        self.settings = Settings(paths=paths)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_overlay_mini_and_classic_styles(self):
        # Starts in Mini mode by default (or configured)
        from dataclasses import replace
        self.settings.app = replace(self.settings.app, recording_window_style=RecordingWindowStyle.MINI)
        overlay = DictationOverlay(self.settings, is_listening_supplier=lambda: False)

        # In Mini mode, fixed size is compact (200x56)
        self.assertEqual(overlay.width(), 200)
        self.assertEqual(overlay.height(), 56)
        self.assertEqual(overlay.root_stack.currentWidget(), overlay.mini_card)

        # Switch to Classic mode
        self.settings.app = replace(self.settings.app, recording_window_style=RecordingWindowStyle.CLASSIC)
        overlay.update_style()

        self.assertEqual(overlay.root_stack.currentWidget(), overlay.classic_card)
        self.assertEqual(overlay.width(), self.settings.ui.popup_width + 24)
        self.assertEqual(overlay.height(), self.settings.ui.popup_height + 24)

    def test_overlay_mini_wpm_transition(self):
        from dataclasses import replace
        self.settings.app = replace(self.settings.app, recording_window_style=RecordingWindowStyle.MINI)
        overlay = DictationOverlay(self.settings, is_listening_supplier=lambda: True)

        # When recording, mini shows live widget (equalizer + text)
        overlay.set_status("[ GRABANDO ]", "#10B981")
        self.assertEqual(overlay.mini_stack.currentWidget(), overlay.mini_live_widget)
        self.assertEqual(overlay.mini_status_text.text(), "Grabando")

        # When stats arrive, mini transitions to WPM widget
        overlay.set_stats(wpm=162.0, time_saved_sec=45.0)
        self.assertEqual(overlay.mini_stack.currentWidget(), overlay.mini_wpm_widget)
        self.assertIn("162 WPM", overlay.mini_wpm_label.text())

        # Next recording resets back to live widget
        overlay.set_status("[ GRABANDO ]", "#10B981")
        self.assertEqual(overlay.mini_stack.currentWidget(), overlay.mini_live_widget)

    def test_web_bridge_recording_window_style_slot(self):
        history_mgr = HistoryManager(self.temp_path / "history.jsonl")
        mock_window = MagicMock()
        mock_style_cb = MagicMock()

        bridge = WebBridge(
            self.settings,
            history_mgr,
            mock_window,
            style_changed_cb=mock_style_cb,
        )

        cfg_str = bridge.getConfig()
        cfg = json.loads(cfg_str)
        self.assertIn("recording_window_style", cfg)

        # Change to classic
        bridge.setRecordingWindowStyle("classic")
        self.assertEqual(self.settings.app.recording_window_style, RecordingWindowStyle.CLASSIC)
        mock_style_cb.assert_called_once()

        # Change to mini
        mock_style_cb.reset_mock()
        bridge.setRecordingWindowStyle("mini")
        self.assertEqual(self.settings.app.recording_window_style, RecordingWindowStyle.MINI)
        mock_style_cb.assert_called_once()


if __name__ == "__main__":
    unittest.main()
