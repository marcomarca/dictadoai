from __future__ import annotations

import json
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
from PySide6.QtWidgets import QApplication

from dictado_ai.audio import AudioCaptureWorker
from dictado_ai.audio_devices import (
    AudioInputDevice,
    negotiate_input_device_params,
    resample_audio,
)
from dictado_ai.config import Settings
from dictado_ai.gui.app import DictationQtApp
from dictado_ai.runtime import AppRuntime


class TestAudioDevicesResilience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_resample_audio_from_48k(self):
        sr_48k = 48000
        # 1.5 seconds tone at 440 Hz
        t = np.linspace(0, 1.5, int(sr_48k * 1.5), endpoint=False, dtype=np.float32)
        signal_48k = np.sin(2 * np.pi * 440 * t).astype(np.float32)

        resampled = resample_audio(signal_48k, orig_sr=48000, target_sr=16000)
        expected_len = int(1.5 * 16000)
        self.assertEqual(len(resampled), expected_len)
        self.assertEqual(resampled.dtype, np.float32)

    def test_resample_audio_from_44k(self):
        sr_44k = 44100
        # 2 seconds tone
        t = np.linspace(0, 2.0, int(sr_44k * 2.0), endpoint=False, dtype=np.float32)
        signal_44k = np.sin(2 * np.pi * 440 * t).astype(np.float32)

        resampled = resample_audio(signal_44k, orig_sr=44100, target_sr=16000)
        expected_len = 32000
        self.assertEqual(len(resampled), expected_len)

    def test_resample_audio_identity(self):
        signal_16k = np.random.randn(16000).astype(np.float32)
        resampled = resample_audio(signal_16k, orig_sr=16000, target_sr=16000)
        self.assertEqual(len(resampled), 16000)
        np.testing.assert_array_equal(signal_16k, resampled)

    def test_resample_audio_empty(self):
        empty = np.array([], dtype=np.float32)
        resampled = resample_audio(empty, orig_sr=48000, target_sr=16000)
        self.assertEqual(len(resampled), 0)

    @patch("dictado_ai.audio_devices.sd.check_input_settings")
    @patch("dictado_ai.audio_devices.sd.query_devices")
    def test_negotiate_input_device_params_wasapi_48k(self, mock_query_devices, mock_check_input):
        mock_query_devices.return_value = {
            "name": "Microphone Array",
            "default_samplerate": 48000.0,
            "max_input_channels": 2,
        }

        # Simular que 16000 Hz falla (WASAPI error) y 48000 Hz tiene éxito
        def check_side_effect(device=None, samplerate=None, channels=None, dtype=None):
            if samplerate == 16000:
                raise RuntimeError("Invalid sample rate [PaErrorCode -9997]")
            if samplerate == 48000 and channels == 1:
                return None
            return None

        mock_check_input.side_effect = check_side_effect

        sr, ch = negotiate_input_device_params(device_index=5, target_sr=16000, channels=1)
        self.assertEqual(sr, 48000)
        self.assertEqual(ch, 1)

    @patch("dictado_ai.audio.sd.InputStream")
    @patch("dictado_ai.audio.find_input_device_by_key")
    def test_worker_auto_fallback_when_device_disconnected(self, mock_find_device, mock_input_stream):
        settings = Settings.default()
        # Configurar un dispositivo específico que ya no existe (desconectado)
        from dataclasses import replace
        settings.audio = replace(
            settings.audio,
            input_device_key="Headset (Redmi Buds 4 Pro)||Windows WASAPI",
            input_device_label="Headset (Redmi Buds 4 Pro)",
        )
        runtime = AppRuntime(settings)

        # find_input_device_by_key devuelve None porque el dispositivo se desconectó
        mock_find_device.return_value = None

        mock_stream_instance = MagicMock()
        fake_frame = np.zeros((512, 1), dtype=np.float32)
        mock_stream_instance.read.return_value = (fake_frame, False)
        mock_stream_instance.__enter__.return_value = mock_stream_instance
        mock_input_stream.return_value = mock_stream_instance

        worker = AudioCaptureWorker(settings, runtime)
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()

        # Iniciar dictado
        runtime.state.set_is_listening(True)
        runtime.listen_event.set()

        time.sleep(0.15)

        # El worker debe haber caído automáticamente a "Sistema predeterminado" (device=None)
        self.assertIsNone(settings.audio.input_device_key)
        self.assertEqual(settings.audio.input_device_label, "Sistema predeterminado")
        self.assertTrue(mock_input_stream.called)

        # Detener dictado
        runtime.state.set_is_listening(False)
        runtime.listen_event.clear()
        runtime.stop_event.set()
        t.join(timeout=1.0)

    @patch("dictado_ai.gui.app.list_input_devices")
    @patch("dictado_ai.gui.app.refresh_audio_devices")
    def test_on_device_hotplug_auto_reassigns_missing_device(self, mock_refresh, mock_list_devices):
        settings = Settings.default()
        from dataclasses import replace
        settings.audio = replace(
            settings.audio,
            input_device_key="Headset (Redmi Buds 4 Pro)||Windows WASAPI",
            input_device_label="Headset (Redmi Buds 4 Pro)",
        )
        runtime = AppRuntime(settings)

        # Los dispositivos enumerados ya no incluyen Redmi Buds
        mock_list_devices.return_value = [
            AudioInputDevice(
                index=1,
                name="Microphone Array",
                hostapi_name="Windows WASAPI",
                max_input_channels=2,
                key="Microphone Array||Windows WASAPI",
                label="Microphone Array",
            )
        ]

        qt_app = DictationQtApp(
            self.app,
            settings,
            runtime,
            toggle_callback=MagicMock(),
            restart_asr_callback=MagicMock(),
            change_mode_callback=MagicMock(),
            change_input_device_callback=MagicMock(),
        )

        # Simular evento hotplug
        qt_app.on_device_hotplug()

        # El dispositivo seleccionado debe haber sido reasignado automáticamente a Sistema predeterminado
        self.assertIsNone(settings.audio.input_device_key)
        self.assertEqual(settings.audio.input_device_label, "Sistema predeterminado")


if __name__ == "__main__":
    unittest.main()
