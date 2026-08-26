from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from dictado_ai.model_downloader import download_whisper_model


class ModelDownloaderTests(unittest.TestCase):
    def test_download_whisper_model_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "models" / "test_model.bin"
            fake_chunks = [b"chunk1_", b"chunk2_", b"chunk3"]
            total_bytes = sum(len(c) for c in fake_chunks)

            mock_response = MagicMock()
            mock_response.headers = {"content-length": str(total_bytes)}
            mock_response.iter_content.return_value = fake_chunks
            mock_response.__enter__.return_value = mock_response
            mock_response.raise_for_status.return_value = None

            progress_reports = []

            def on_progress(downloaded, total, percent):
                progress_reports.append((downloaded, total, percent))

            with patch("requests.Session.get", return_value=mock_response):
                success = download_whisper_model(
                    target_path=target_path,
                    url="https://example.com/model.bin",
                    progress_callback=on_progress,
                )

            self.assertTrue(success)
            self.assertTrue(target_path.exists())
            self.assertEqual(target_path.read_bytes(), b"chunk1_chunk2_chunk3")
            self.assertFalse(target_path.with_suffix(".bin.part").exists())
            self.assertTrue(len(progress_reports) > 0)

    def test_download_whisper_model_http_error_cleans_up(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target_path = Path(temp_dir) / "models" / "failed_model.bin"

            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = RuntimeError("404 Not Found")
            mock_response.__enter__.return_value = mock_response

            with patch("requests.Session.get", return_value=mock_response):
                success = download_whisper_model(
                    target_path=target_path,
                    url="https://example.com/notfound.bin",
                )

            self.assertFalse(success)
            self.assertFalse(target_path.exists())
            self.assertFalse(target_path.with_suffix(".bin.part").exists())
