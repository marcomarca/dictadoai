from __future__ import annotations

import io
import threading
import time
import unittest
from pathlib import Path

import numpy as np

from dictado_ai.asr import AsrClientRouter, GroqWhisperClient
from dictado_ai.config import ApiKeys, AsrConfig, AsrProvider, GroqAsrConfig, PathsConfig, Settings
from dictado_ai.runtime import AppRuntime


def make_settings(**overrides) -> Settings:
    values = {"paths": PathsConfig(project_root=Path.cwd())}
    values.update(overrides)
    return Settings(**values)


class GroqLocalPrewarmTests(unittest.TestCase):
    def test_prewarm_local_returns_false_without_api_key(self) -> None:
        settings = make_settings(api_keys=ApiKeys(groq=""))
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)

        def fail_get_client():
            raise AssertionError("_get_client should not be called without API key")

        client._get_client = fail_get_client

        self.assertIs(client.prewarm_local(), False)

    def test_prewarm_local_creates_client_without_api_request(self) -> None:
        class FakeTranscriptions:
            def create(self, **kwargs):
                raise AssertionError("prewarm_local must not call Groq API")

        class FakeAudio:
            def __init__(self):
                self.transcriptions = FakeTranscriptions()

        class FakeGroq:
            def __init__(self):
                self.audio = FakeAudio()

        settings = make_settings(
            api_keys=ApiKeys(groq="dummy"),
            groq_asr=GroqAsrConfig(prewarm_wav_encoder=False),
        )
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)
        fake = FakeGroq()
        client._get_client = lambda: fake

        self.assertIs(client.prewarm_local(), True)

    def test_prewarm_local_warms_wav_encoder_when_enabled(self) -> None:
        settings = make_settings(
            api_keys=ApiKeys(groq="dummy"),
            groq_asr=GroqAsrConfig(prewarm_wav_encoder=True, prewarm_audio_ms=200),
        )
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)
        client._get_client = lambda: object()
        calls = {"count": 0, "length": 0}

        def fake_audio_to_wav_bytes(audio):
            calls["count"] += 1
            calls["length"] = len(audio)
            return io.BytesIO(b"fake-wav")

        client.audio_to_wav_bytes = fake_audio_to_wav_bytes

        self.assertIs(client.prewarm_local(), True)
        self.assertEqual(calls["count"], 1)
        self.assertGreater(calls["length"], 0)

    def test_prewarm_local_skips_wav_encoder_when_disabled(self) -> None:
        settings = make_settings(
            api_keys=ApiKeys(groq="dummy"),
            groq_asr=GroqAsrConfig(prewarm_wav_encoder=False),
        )
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)
        client._get_client = lambda: object()

        def fail_audio_to_wav_bytes(audio):
            raise AssertionError("audio_to_wav_bytes should not be called")

        client.audio_to_wav_bytes = fail_audio_to_wav_bytes

        self.assertIs(client.prewarm_local(), True)

    def test_prewarm_local_returns_false_if_client_unavailable(self) -> None:
        settings = make_settings(api_keys=ApiKeys(groq="dummy"))
        runtime = AppRuntime(settings)
        client = GroqWhisperClient(settings, runtime)
        client._get_client = lambda: None

        self.assertIs(client.prewarm_local(), False)

    def test_router_prewarm_async_launches_thread_for_groq(self) -> None:
        class FakePrewarmClient:
            def __init__(self):
                self.called = threading.Event()

            def transcribe(self, audio_data, prompt="", is_partial=False):
                raise NotImplementedError

            def warmup(self):
                pass

            def prewarm_local(self):
                self.called.set()
                return True

        settings = make_settings()
        runtime = AppRuntime(settings)
        router = AsrClientRouter(settings, runtime)
        fake = FakePrewarmClient()
        router._client = fake

        launched = router.prewarm_async()

        self.assertIs(launched, True)
        self.assertIs(fake.called.wait(1.0), True)

    def test_router_prewarm_async_returns_false_for_local_provider(self) -> None:
        settings = make_settings(asr=AsrConfig(provider=AsrProvider.WHISPER_CPP))
        runtime = AppRuntime(settings)
        router = AsrClientRouter(settings, runtime)

        self.assertIs(router.prewarm_async(), False)

    def test_router_prewarm_async_returns_false_when_disabled(self) -> None:
        settings = make_settings(groq_asr=GroqAsrConfig(prewarm_enabled=False))
        runtime = AppRuntime(settings)
        router = AsrClientRouter(settings, runtime)

        self.assertIs(router.prewarm_async(), False)

    def test_router_prewarm_async_deduplicates_concurrent_calls(self) -> None:
        class BlockingPrewarmClient:
            def __init__(self):
                self.started = threading.Event()
                self.release = threading.Event()
                self.calls = 0

            def transcribe(self, audio_data, prompt="", is_partial=False):
                raise NotImplementedError

            def warmup(self):
                pass

            def prewarm_local(self):
                self.calls += 1
                self.started.set()
                self.release.wait(1.0)
                return True

        settings = make_settings()
        runtime = AppRuntime(settings)
        router = AsrClientRouter(settings, runtime)
        fake = BlockingPrewarmClient()
        router._client = fake

        self.assertIs(router.prewarm_async(), True)
        self.assertIs(fake.started.wait(1.0), True)
        self.assertIs(router.prewarm_async(), False)
        fake.release.set()
        time.sleep(0.05)
        self.assertEqual(fake.calls, 1)

    def test_router_prewarm_async_resets_flag_after_completion(self) -> None:
        class FastPrewarmClient:
            def __init__(self):
                self.calls = 0
                self.done = threading.Event()

            def transcribe(self, audio_data, prompt="", is_partial=False):
                raise NotImplementedError

            def warmup(self):
                pass

            def prewarm_local(self):
                self.calls += 1
                self.done.set()
                return True

        settings = make_settings()
        runtime = AppRuntime(settings)
        router = AsrClientRouter(settings, runtime)
        fake = FastPrewarmClient()
        router._client = fake

        self.assertIs(router.prewarm_async(), True)
        self.assertIs(fake.done.wait(1.0), True)
        time.sleep(0.05)
        fake.done = threading.Event()
        self.assertIs(router.prewarm_async(), True)
        self.assertIs(fake.done.wait(1.0), True)
        self.assertGreaterEqual(fake.calls, 2)


if __name__ == "__main__":
    unittest.main()
