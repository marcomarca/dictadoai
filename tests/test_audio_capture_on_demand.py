from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from dictado_ai.audio import AudioCaptureWorker
from dictado_ai.config import Settings
from dictado_ai.runtime import AppRuntime


class TestAudioCaptureOnDemand(unittest.TestCase):
    def setUp(self):
        self.settings = Settings.default()
        self.runtime = AppRuntime(self.settings)

    @patch("dictado_ai.audio.sd.InputStream")
    def test_worker_idle_does_not_open_stream(self, mock_input_stream):
        worker = AudioCaptureWorker(self.settings, self.runtime)

        # Iniciar worker en hilo secundario mientras is_listening es False
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()

        time.sleep(0.15)
        # El stream NO debe haberse abierto
        mock_input_stream.assert_not_called()

        self.runtime.stop_event.set()
        t.join(timeout=1.0)

    @patch("dictado_ai.audio.sd.InputStream")
    def test_worker_opens_stream_on_listen_and_closes_on_stop(self, mock_input_stream):
        mock_stream_instance = MagicMock()
        # Simular lectura de frames de audio
        fake_frame = np.zeros((512, 1), dtype=np.float32)
        mock_stream_instance.read.return_value = (fake_frame, False)
        mock_stream_instance.__enter__.return_value = mock_stream_instance

        mock_input_stream.return_value = mock_stream_instance

        worker = AudioCaptureWorker(self.settings, self.runtime)
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()

        # Iniciar dictado
        self.runtime.state.set_is_listening(True)
        self.runtime.listen_event.set()

        # Dar tiempo a que el worker abra el stream y lea al menos un frame
        time.sleep(0.1)
        mock_input_stream.assert_called_once()
        self.assertTrue(mock_stream_instance.read.called)

        # Detener dictado
        self.runtime.state.set_is_listening(False)
        self.runtime.listen_event.clear()

        # Dar tiempo a que el context manager __exit__ se ejecute
        time.sleep(0.1)
        self.assertTrue(mock_stream_instance.__exit__.called)

        self.runtime.stop_event.set()
        t.join(timeout=1.0)


if __name__ == "__main__":
    unittest.main()
