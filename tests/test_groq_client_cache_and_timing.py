from __future__ import annotations

import builtins
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from dictado_ai.asr import AsrFailureKind, GroqWhisperClient
from dictado_ai.config import ApiKeys, PathsConfig, Settings, VadConfig
from dictado_ai.runtime import AppRuntime


def make_settings(**overrides) -> Settings:
    values = {"paths": PathsConfig(project_root=Path.cwd())}
    values.update(overrides)
    return Settings(**values)


class GroqClientCacheAndTimingTests(unittest.TestCase):
    def test_get_client_returns_none_without_api_key(self) -> None:
        settings = make_settings(api_keys=ApiKeys(groq=""))
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)

        self.assertIsNone(client._get_client())

    def test_get_client_caches_groq_client(self) -> None:
        class FakeGroq:
            instances = []

            def __init__(self, api_key=None):
                self.api_key = api_key
                FakeGroq.instances.append(self)

        fake_module = types.SimpleNamespace(Groq=FakeGroq)

        with patch.dict(sys.modules, {"groq": fake_module}):
            settings = make_settings(api_keys=ApiKeys(groq="dummy"))
            runtime = AppRuntime(settings)
            client = GroqWhisperClient(settings, runtime)

            first = client._get_client()
            second = client._get_client()

        self.assertIs(first, second)
        self.assertEqual(len(FakeGroq.instances), 1)
        self.assertEqual(FakeGroq.instances[0].api_key, "dummy")

    def test_get_client_returns_none_when_groq_sdk_missing(self) -> None:
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "groq":
                raise ImportError("missing groq")
            return original_import(name, *args, **kwargs)

        settings = make_settings(api_keys=ApiKeys(groq="dummy"))
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)

        with patch("builtins.__import__", side_effect=fake_import):
            self.assertIsNone(client._get_client())

    def test_transcribe_uses_cached_client_and_logs_timing(self) -> None:
        class FakeTranscriptions:
            def __init__(self):
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return {"text": "hola mundo"}

        class FakeAudio:
            def __init__(self):
                self.transcriptions = FakeTranscriptions()

        class FakeGroq:
            def __init__(self):
                self.audio = FakeAudio()

        settings = make_settings(api_keys=ApiKeys(groq="dummy"), vad=VadConfig(enabled=False))
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)
        fake = FakeGroq()
        client._get_client = lambda: fake
        audio = np.zeros(16000, dtype=np.float32)

        with self.assertLogs("dictado_ai.asr", level="INFO") as cm:
            result = client.transcribe(audio)

        self.assertIs(result.ok, True)
        self.assertEqual(result.text.lower(), "hola mundo")
        self.assertEqual(len(fake.audio.transcriptions.calls), 1)
        timing_lines = [line for line in cm.output if "Groq ASR timing" in line]
        self.assertTrue(timing_lines)
        self.assertTrue(any("wav=" in line for line in timing_lines))
        self.assertTrue(any("client=" in line for line in timing_lines))
        self.assertTrue(any("http=" in line for line in timing_lines))
        self.assertTrue(any("postprocess=" in line for line in timing_lines))
        self.assertTrue(any("total=" in line for line in timing_lines))

    def test_transcribe_logs_timing_when_missing_api_key(self) -> None:
        settings = make_settings(api_keys=ApiKeys(groq=""), vad=VadConfig(enabled=False))
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)
        audio = np.zeros(16000, dtype=np.float32)

        with self.assertLogs("dictado_ai.asr", level="INFO") as cm:
            result = client.transcribe(audio)

        self.assertIs(result.ok, False)
        self.assertEqual(result.failure_kind, AsrFailureKind.MISSING_API_KEY)
        self.assertTrue(any("Groq ASR timing failed" in line for line in cm.output))
        self.assertTrue(any("MISSING_API_KEY" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
