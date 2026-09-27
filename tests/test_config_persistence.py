import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dictado_ai.config import (
    Settings,
    PathsConfig,
    AppConfig,
    AudioConfig,
    AsrConfig,
    GroqAsrConfig,
    OllamaConfig,
    LlmProvider,
    AsrProvider,
    AsrDevice,
    DictationMode,
    GroqAsrModel,
    RecordingWindowStyle,
)


class TestConfigPersistence(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_paths_config_app_data_dir(self):
        # Default with APPDATA env var
        with patch.dict(os.environ, {"APPDATA": str(self.temp_path)}):
            paths = PathsConfig(project_root=self.temp_path)
            self.assertEqual(paths.app_data_dir, self.temp_path / "DictadoAI")
            self.assertEqual(paths.config_file, self.temp_path / "DictadoAI" / "config.json")

        # Overridden user_data_dir
        custom_data_dir = self.temp_path / "custom_data"
        paths_custom = PathsConfig(project_root=self.temp_path, user_data_dir=custom_data_dir)
        self.assertEqual(paths_custom.app_data_dir, custom_data_dir)
        self.assertEqual(paths_custom.config_file, custom_data_dir / "config.json")

    def test_to_dict_and_apply_dict(self):
        paths = PathsConfig(project_root=self.temp_path, user_data_dir=self.temp_path)
        settings = Settings(paths=paths)

        # Mutate in memory
        from dataclasses import replace
        settings.app = replace(
            settings.app,
            auto_copy_clipboard=True,
            auto_pause_media=False,
            dictation_mode=DictationMode.PUSH_TO_TALK,
            recording_window_style=RecordingWindowStyle.CLASSIC,
            hotkey="ctrl+shift+d",
            typing_speed_wpm=95,
        )
        settings.audio = replace(
            settings.audio,
            input_device_key="mic-uuid-123",
            input_device_label="Microfono Externo USB",
        )
        settings.active_provider = LlmProvider.GROQ
        settings.asr = replace(
            settings.asr,
            provider=AsrProvider.WHISPER_CPP,
            device=AsrDevice.GPU,
            language="es",
        )
        settings.groq_asr = replace(
            settings.groq_asr,
            model=GroqAsrModel.WHISPER_LARGE_V3,
        )

        data = settings.to_dict()
        self.assertEqual(data["version"], 1)
        self.assertTrue(data["app"]["auto_copy_clipboard"])
        self.assertFalse(data["app"]["auto_pause_media"])
        self.assertEqual(data["app"]["dictation_mode"], DictationMode.PUSH_TO_TALK.value)
        self.assertEqual(data["app"]["recording_window_style"], RecordingWindowStyle.CLASSIC.value)
        self.assertEqual(data["app"]["hotkey"], "ctrl+shift+d")
        self.assertEqual(data["app"]["typing_speed_wpm"], 95)
        self.assertEqual(data["audio"]["input_device_key"], "mic-uuid-123")
        self.assertEqual(data["audio"]["input_device_label"], "Microfono Externo USB")
        self.assertEqual(data["active_provider"], LlmProvider.GROQ.value)
        self.assertEqual(data["asr"]["provider"], AsrProvider.WHISPER_CPP.value)
        self.assertEqual(data["asr"]["device"], AsrDevice.GPU.value)
        self.assertEqual(data["groq_asr"]["model"], GroqAsrModel.WHISPER_LARGE_V3.value)

        # Apply to a fresh settings instance
        fresh_settings = Settings(paths=paths)
        fresh_settings.apply_dict(data)

        self.assertTrue(fresh_settings.app.auto_copy_clipboard)
        self.assertFalse(fresh_settings.app.auto_pause_media)
        self.assertEqual(fresh_settings.app.dictation_mode, DictationMode.PUSH_TO_TALK)
        self.assertEqual(fresh_settings.app.recording_window_style, RecordingWindowStyle.CLASSIC)
        self.assertEqual(fresh_settings.app.hotkey, "ctrl+shift+d")
        self.assertEqual(fresh_settings.app.typing_speed_wpm, 95)
        self.assertEqual(fresh_settings.audio.input_device_key, "mic-uuid-123")
        self.assertEqual(fresh_settings.audio.input_device_label, "Microfono Externo USB")
        self.assertEqual(fresh_settings.active_provider, LlmProvider.GROQ)
        self.assertEqual(fresh_settings.asr.provider, AsrProvider.WHISPER_CPP)
        self.assertEqual(fresh_settings.asr.device, AsrDevice.GPU)
        self.assertEqual(fresh_settings.groq_asr.model, GroqAsrModel.WHISPER_LARGE_V3)

    def test_save_and_load_file(self):
        config_file = self.temp_path / "appdata_mock" / "config.json"
        paths = PathsConfig(project_root=self.temp_path, user_data_dir=config_file.parent)
        settings = Settings(paths=paths)

        # Default auto_copy_clipboard is False
        self.assertFalse(settings.app.auto_copy_clipboard)

        # Change and save
        from dataclasses import replace
        settings.app = replace(settings.app, auto_copy_clipboard=True)
        saved = settings.save()
        self.assertTrue(saved)
        self.assertTrue(config_file.exists())

        # Load into another instance
        loaded_settings = Settings(paths=paths)
        loaded = loaded_settings.load()
        self.assertTrue(loaded)
        self.assertTrue(loaded_settings.app.auto_copy_clipboard)

    def test_load_corrupt_json_graceful_recovery(self):
        config_file = self.temp_path / "config.json"
        config_file.write_text("{corrupt: json -- invalid", encoding="utf-8")

        paths = PathsConfig(project_root=self.temp_path, user_data_dir=self.temp_path)
        settings = Settings(paths=paths)
        # Loading corrupt json should not throw, should return False, and keep defaults
        result = settings.load()
        self.assertFalse(result)
        self.assertFalse(settings.app.auto_copy_clipboard)


if __name__ == "__main__":
    unittest.main()
