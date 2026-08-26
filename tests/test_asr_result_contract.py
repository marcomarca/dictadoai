from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from dictado_ai.asr import AsrFailureKind, AsrResult, BaseAsrClient, GroqWhisperClient
from dictado_ai.config import ApiKeys, GroqAsrConfig, PathsConfig, Settings, VadConfig
from dictado_ai.runtime import AppRuntime


def make_settings(**overrides) -> Settings:
    values = {"paths": PathsConfig(project_root=Path.cwd())}
    values.update(overrides)
    return Settings(**values)


class AsrResultContractTests(unittest.TestCase):
    def test_success_contract(self) -> None:
        result = AsrResult.success("hola", "hola")

        self.assertIs(result.ok, True)
        self.assertIs(bool(result), True)
        self.assertIsNone(result.failure_kind)

        raw, text = result
        self.assertEqual(raw, "hola")
        self.assertEqual(text, "hola")

    def test_failure_contract(self) -> None:
        result = AsrResult.failure(
            AsrFailureKind.TIMEOUT,
            retryable=True,
            fallback_allowed=True,
            user_message="Timeout comunicando con ASR.",
        )

        self.assertIs(result.ok, False)
        self.assertIs(bool(result), False)
        self.assertEqual(result.failure_kind, AsrFailureKind.TIMEOUT)
        self.assertIs(result.retryable, True)
        self.assertIs(result.fallback_allowed, True)
        self.assertEqual(result.user_message, "Timeout comunicando con ASR.")

    def test_postprocess_raw_text_valid_text(self) -> None:
        settings = make_settings(vad=VadConfig(enabled=False))
        runtime = AppRuntime(settings)
        client = BaseAsrClient(settings, runtime)
        audio = np.zeros(settings.audio.sample_rate, dtype=np.float32)

        result = client._postprocess_raw_text("hola mundo", audio, is_partial=False)

        self.assertIs(result.ok, True)
        self.assertEqual(result.raw_text, "hola mundo")
        self.assertEqual(result.text.lower(), "hola mundo")

    def test_postprocess_raw_text_empty_text(self) -> None:
        settings = make_settings(vad=VadConfig(enabled=False))
        runtime = AppRuntime(settings)
        client = BaseAsrClient(settings, runtime)
        audio = np.zeros(settings.audio.sample_rate, dtype=np.float32)

        result = client._postprocess_raw_text("", audio, is_partial=False)

        self.assertIs(result.ok, False)
        self.assertEqual(result.failure_kind, AsrFailureKind.NO_SPEECH)
        self.assertIs(result.fallback_allowed, False)
        self.assertIs(result.retryable, False)

    def test_groq_transcribe_missing_api_key(self) -> None:
        settings = make_settings(api_keys=ApiKeys(groq=""))
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)
        audio = np.zeros(settings.audio.sample_rate, dtype=np.float32)

        result = client.transcribe(audio)

        self.assertIs(result.ok, False)
        self.assertEqual(result.failure_kind, AsrFailureKind.MISSING_API_KEY)
        self.assertIs(result.fallback_allowed, True)
        self.assertIs(result.retryable, False)

    def test_groq_transcribe_payload_too_large(self) -> None:
        settings = make_settings(
            api_keys=ApiKeys(groq="dummy"),
            groq_asr=GroqAsrConfig(max_upload_mb=0.000001),
            vad=VadConfig(enabled=False),
        )
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)
        client._get_client = lambda: object()
        audio = np.zeros(settings.audio.sample_rate, dtype=np.float32)

        result = client.transcribe(audio)

        self.assertEqual(result.failure_kind, AsrFailureKind.PAYLOAD_TOO_LARGE)
        self.assertIs(result.fallback_allowed, True)
        self.assertIs(result.retryable, False)

    def test_groq_transcribe_successful_fake_client(self) -> None:
        class FakeTranscriptions:
            def __init__(self):
                self.kwargs = None

            def create(self, **kwargs):
                self.kwargs = kwargs
                return {"text": "hola mundo"}

        class FakeAudio:
            def __init__(self):
                self.transcriptions = FakeTranscriptions()

        class FakeGroqClient:
            def __init__(self):
                self.audio = FakeAudio()

        settings = make_settings(
            api_keys=ApiKeys(groq="dummy"),
            vad=VadConfig(enabled=False),
        )
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)
        fake = FakeGroqClient()
        client._get_client = lambda: fake
        audio = np.zeros(settings.audio.sample_rate, dtype=np.float32)

        result = client.transcribe(audio)

        self.assertIs(result.ok, True)
        self.assertEqual(result.raw_text, "hola mundo")
        self.assertEqual(result.text.lower(), "hola mundo")
        self.assertEqual(fake.audio.transcriptions.kwargs["model"], "whisper-large-v3-turbo")
        self.assertEqual(fake.audio.transcriptions.kwargs["response_format"], "verbose_json")


if __name__ == "__main__":
    unittest.main()
