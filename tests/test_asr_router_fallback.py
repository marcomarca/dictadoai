from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from dictado_ai.asr import AsrClientRouter, AsrFailureKind, AsrResult
from dictado_ai.config import AsrConfig, AsrProvider, GroqAsrConfig, PathsConfig, Settings
from dictado_ai.runtime import AppRuntime


def make_settings(**overrides) -> Settings:
    values = {"paths": PathsConfig(project_root=Path.cwd())}
    values.update(overrides)
    return Settings(**values)


class FakeAsrClient:
    def __init__(self, result: AsrResult):
        self.result = result
        self.calls = []

    def transcribe(self, audio_data, prompt: str = "", is_partial: bool = False) -> AsrResult:
        self.calls.append(
            {
                "audio_data": audio_data,
                "prompt": prompt,
                "is_partial": is_partial,
            }
        )
        return self.result

    def warmup(self) -> None:
        pass


def drain_ui_texts(runtime: AppRuntime) -> list[str]:
    texts = []
    while not runtime.ui_queue.empty():
        msg = runtime.ui_queue.get_nowait()
        if msg.kind == "text":
            texts.append(msg.text)
    return texts


def network_failure() -> AsrResult:
    return AsrResult.failure(
        AsrFailureKind.NETWORK_ERROR,
        retryable=True,
        fallback_allowed=True,
        user_message="Fallo de red comunicando con Groq ASR.",
    )


class AsrRouterFallbackTests(unittest.TestCase):
    def test_groq_success_does_not_use_fallback(self) -> None:
        settings = make_settings()
        runtime = AppRuntime(settings)
        calls = {"ensure": 0}

        def ensure_local_ready() -> bool:
            calls["ensure"] += 1
            return True

        router = AsrClientRouter(settings, runtime, ensure_local_ready=ensure_local_ready)
        primary = FakeAsrClient(AsrResult.success("hola", "hola"))
        local = FakeAsrClient(AsrResult.success("local", "local"))
        router._client = primary
        router._build_local_fallback_client = lambda: local

        result = router.transcribe(np.zeros(160, dtype=np.float32))

        self.assertIs(result.ok, True)
        self.assertEqual(result.text, "hola")
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(len(local.calls), 0)
        self.assertEqual(calls["ensure"], 0)

    def test_groq_no_speech_does_not_use_fallback(self) -> None:
        settings = make_settings()
        runtime = AppRuntime(settings)
        calls = {"ensure": 0}

        def ensure_local_ready() -> bool:
            calls["ensure"] += 1
            return True

        router = AsrClientRouter(settings, runtime, ensure_local_ready=ensure_local_ready)
        primary = FakeAsrClient(
            AsrResult.failure(
                AsrFailureKind.NO_SPEECH,
                retryable=False,
                fallback_allowed=False,
                user_message="No se detectó voz útil.",
            )
        )
        local = FakeAsrClient(AsrResult.success("local", "local"))
        router._client = primary
        router._build_local_fallback_client = lambda: local

        result = router.transcribe(np.zeros(160, dtype=np.float32))

        self.assertEqual(result.failure_kind, AsrFailureKind.NO_SPEECH)
        self.assertEqual(len(local.calls), 0)
        self.assertEqual(calls["ensure"], 0)

    def test_groq_network_error_uses_local_fallback_when_ready(self) -> None:
        settings = make_settings()
        runtime = AppRuntime(settings)
        calls = {"ensure": 0}

        def ensure_local_ready() -> bool:
            calls["ensure"] += 1
            return True

        router = AsrClientRouter(settings, runtime, ensure_local_ready=ensure_local_ready)
        primary = FakeAsrClient(network_failure())
        local = FakeAsrClient(AsrResult.success("texto local", "texto local"))
        router._client = primary
        router._build_local_fallback_client = lambda: local

        result = router.transcribe(np.zeros(160, dtype=np.float32), prompt="contexto", is_partial=True)

        self.assertIs(result.ok, True)
        self.assertEqual(result.text, "texto local")
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(len(local.calls), 1)
        self.assertEqual(calls["ensure"], 1)
        self.assertEqual(local.calls[0]["prompt"], "contexto")
        self.assertIs(local.calls[0]["is_partial"], True)

    def test_groq_failure_returns_primary_when_fallback_disabled(self) -> None:
        settings = make_settings(groq_asr=GroqAsrConfig(fallback_to_local=False))
        runtime = AppRuntime(settings)
        calls = {"ensure": 0}

        def ensure_local_ready() -> bool:
            calls["ensure"] += 1
            return True

        router = AsrClientRouter(settings, runtime, ensure_local_ready=ensure_local_ready)
        primary = FakeAsrClient(network_failure())
        local = FakeAsrClient(AsrResult.success("local", "local"))
        router._client = primary
        router._build_local_fallback_client = lambda: local

        result = router.transcribe(np.zeros(160, dtype=np.float32))

        self.assertIs(result, primary.result)
        self.assertEqual(len(local.calls), 0)
        self.assertEqual(calls["ensure"], 0)

    def test_groq_failure_returns_primary_when_no_ensure_callback(self) -> None:
        settings = make_settings()
        runtime = AppRuntime(settings)
        router = AsrClientRouter(settings, runtime)
        primary = FakeAsrClient(network_failure())
        local = FakeAsrClient(AsrResult.success("local", "local"))
        router._client = primary
        router._build_local_fallback_client = lambda: local

        result = router.transcribe(np.zeros(160, dtype=np.float32))

        self.assertIs(result, primary.result)
        self.assertEqual(len(local.calls), 0)
        self.assertIn(
            "Fallback local no configurado; se conserva el fallo de Groq ASR.",
            drain_ui_texts(runtime),
        )

    def test_groq_failure_returns_primary_when_local_not_ready(self) -> None:
        settings = make_settings()
        runtime = AppRuntime(settings)
        router = AsrClientRouter(settings, runtime, ensure_local_ready=lambda: False)
        primary = FakeAsrClient(network_failure())
        local = FakeAsrClient(AsrResult.success("local", "local"))
        router._client = primary
        router._build_local_fallback_client = lambda: local

        result = router.transcribe(np.zeros(160, dtype=np.float32))

        self.assertIs(result, primary.result)
        self.assertEqual(len(local.calls), 0)
        self.assertIn(
            "Whisper local no está disponible para fallback; se conserva el fallo de Groq ASR.",
            drain_ui_texts(runtime),
        )

    def test_groq_failure_returns_primary_when_ensure_callback_raises(self) -> None:
        settings = make_settings()
        runtime = AppRuntime(settings)

        def ensure_local_ready() -> bool:
            raise RuntimeError("boom")

        router = AsrClientRouter(settings, runtime, ensure_local_ready=ensure_local_ready)
        primary = FakeAsrClient(network_failure())
        local = FakeAsrClient(AsrResult.success("local", "local"))
        router._client = primary
        router._build_local_fallback_client = lambda: local

        result = router.transcribe(np.zeros(160, dtype=np.float32))

        self.assertIs(result, primary.result)
        self.assertEqual(len(local.calls), 0)
        self.assertTrue(
            any("No se pudo preparar Whisper local como fallback" in text for text in drain_ui_texts(runtime))
        )

    def test_groq_failure_returns_local_failure_when_local_also_fails(self) -> None:
        settings = make_settings()
        runtime = AppRuntime(settings)
        router = AsrClientRouter(settings, runtime, ensure_local_ready=lambda: True)
        primary = FakeAsrClient(network_failure())
        local = FakeAsrClient(
            AsrResult.failure(
                AsrFailureKind.SERVER_ERROR,
                retryable=True,
                fallback_allowed=False,
                user_message="Whisper local respondió con error HTTP 500.",
            )
        )
        router._client = primary
        router._build_local_fallback_client = lambda: local

        result = router.transcribe(np.zeros(160, dtype=np.float32))

        self.assertIs(result.ok, False)
        self.assertEqual(result.failure_kind, AsrFailureKind.SERVER_ERROR)
        self.assertEqual(len(primary.calls), 1)
        self.assertEqual(len(local.calls), 1)
        self.assertIn("Groq ASR falló y Whisper local también falló.", drain_ui_texts(runtime))

    def test_local_provider_never_uses_router_fallback(self) -> None:
        settings = make_settings(asr=AsrConfig(provider=AsrProvider.WHISPER_CPP))
        runtime = AppRuntime(settings)
        calls = {"ensure": 0}

        def ensure_local_ready() -> bool:
            calls["ensure"] += 1
            return True

        router = AsrClientRouter(settings, runtime, ensure_local_ready=ensure_local_ready)
        primary = FakeAsrClient(network_failure())
        local = FakeAsrClient(AsrResult.success("local", "local"))
        router._client = primary
        router._build_local_fallback_client = lambda: local

        result = router.transcribe(np.zeros(160, dtype=np.float32))

        self.assertIs(result, primary.result)
        self.assertEqual(len(local.calls), 0)
        self.assertEqual(calls["ensure"], 0)


if __name__ == "__main__":
    unittest.main()
