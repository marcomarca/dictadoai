from __future__ import annotations

import io
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Protocol

import numpy as np

from .config import AsrProvider, GroqAsrModel, Settings
from .runtime import AppRuntime
from .text_processing import postprocess_transcript, is_suspicious_transcript

if TYPE_CHECKING:
    from .vad import SileroVadVerifier

logger = logging.getLogger(__name__)


class AsrFailureKind(str, Enum):
    NO_SPEECH = "NO_SPEECH"
    MISSING_API_KEY = "MISSING_API_KEY"
    SDK_NOT_INSTALLED = "SDK_NOT_INSTALLED"
    AUTH_ERROR = "AUTH_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    NETWORK_ERROR = "NETWORK_ERROR"
    TIMEOUT = "TIMEOUT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    SERVER_ERROR = "SERVER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class AsrResult:
    ok: bool
    raw_text: str = ""
    text: str = ""
    failure_kind: AsrFailureKind | None = None
    retryable: bool = False
    fallback_allowed: bool = False
    user_message: str = ""
    details: dict[str, str] = field(default_factory=dict)

    @classmethod
    def success(cls, raw_text: str, text: str) -> "AsrResult":
        return cls(ok=True, raw_text=raw_text, text=text)

    @classmethod
    def failure(
        cls,
        failure_kind: AsrFailureKind,
        *,
        retryable: bool = False,
        fallback_allowed: bool = False,
        user_message: str = "",
        details: dict[str, str] | None = None,
    ) -> "AsrResult":
        return cls(
            ok=False,
            failure_kind=failure_kind,
            retryable=retryable,
            fallback_allowed=fallback_allowed,
            user_message=user_message,
            details=details or {},
        )

    def __bool__(self) -> bool:
        return self.ok and bool(self.text)

    def __iter__(self):
        yield self.raw_text
        yield self.text


class AsrClient(Protocol):
    def transcribe(self, audio_data: np.ndarray, prompt: str = "", is_partial: bool = False) -> AsrResult:
        ...

    def warmup(self) -> None:
        ...


class BaseAsrClient:
    def __init__(self, settings: Settings, runtime: AppRuntime):
        self.settings = settings
        self.runtime = runtime
        self._vad_verifier: SileroVadVerifier | None = None

    @property
    def vad_verifier(self) -> SileroVadVerifier:
        # Carga lazy: evita pagar el coste de Silero durante el arranque.
        if self._vad_verifier is None:
            from .vad import SileroVadVerifier

            self._vad_verifier = SileroVadVerifier(self.settings)
        return self._vad_verifier

    def audio_to_wav_bytes(self, audio_data: np.ndarray) -> io.BytesIO:
        import scipy.io.wavfile as wavfile

        clipped = np.clip(audio_data, -1.0, 1.0)
        audio_int16 = (clipped * 32767.0).astype(np.int16)
        wav_io = io.BytesIO()
        wavfile.write(wav_io, self.settings.audio.sample_rate, audio_int16)
        wav_io.seek(0)
        return wav_io

    def _postprocess_raw_text(
        self,
        raw_text: str,
        audio_data: np.ndarray,
        is_partial: bool = False,
    ) -> AsrResult:
        duration_s = len(audio_data) / self.settings.audio.sample_rate
        raw_text = (raw_text or "").strip()
        logger.debug("Texto bruto recibido del ASR: '%s'", raw_text)

        force_allow = False
        if self.settings.vad.enabled and not is_partial:
            has_suspicious_pattern = is_suspicious_transcript(raw_text, self.settings.vad.suspicious_patterns)

            word_count = len(re.findall(r"\w+", raw_text))
            wpm = (word_count / duration_s) * 60 if duration_s > 0 else 0
            is_too_slow = duration_s > 3.0 and wpm < self.settings.vad.min_wpm_trigger and word_count > 0

            if has_suspicious_pattern or is_too_slow:
                trigger_reason = (
                    "PATRÓN SOSPECHOSO"
                    if has_suspicious_pattern
                    else f"BAJA DENSIDAD ({wpm:.1f} WPM < {self.settings.vad.min_wpm_trigger})"
                )
                logger.info("VAD Trigger activado [%s] para texto: '%s'", trigger_reason, raw_text)

                if self.vad_verifier.contains_speech(audio_data):
                    logger.info("VAD: Voz humana confirmada. Guardando transcripción.")
                    force_allow = True
                else:
                    logger.warning("VAD: No se detectó voz humana. Descartando alucinación.")
                    return AsrResult.failure(
                        AsrFailureKind.NO_SPEECH,
                        retryable=False,
                        fallback_allowed=False,
                        user_message="No se detectó voz útil.",
                    )
            else:
                logger.debug("VAD: Texto aceptado directamente (WPM: %.1f, sin patrones sospechosos)", wpm)

        processed_text = postprocess_transcript(
            raw_text,
            audio_duration_s=duration_s,
            is_partial=is_partial,
            runtime_state=self.runtime.state,
            force_allow=force_allow,
        )
        logger.debug("Texto procesado: '%s'", processed_text)
        if not processed_text:
            return AsrResult.failure(
                AsrFailureKind.NO_SPEECH,
                retryable=False,
                fallback_allowed=False,
                user_message="No se detectó voz útil.",
            )
        return AsrResult.success(raw_text=raw_text, text=processed_text)

    def warmup(self) -> None:
        return None


class WhisperCppClient(BaseAsrClient):
    def transcribe(self, audio_data: np.ndarray, prompt: str = "", is_partial: bool = False) -> AsrResult:
        import requests

        wav_io = self.audio_to_wav_bytes(audio_data)
        files = {"file": ("audio.wav", wav_io, "audio/wav")}
        data = {
            "response_format": "json",
            "language": "auto",
            "temperature": f"{self.settings.asr.temperature}",
            "temperature_inc": "0.2",
            "suppress_nst": "true",
            "no_timestamps": "true",
            "beam_size": "5",
            "best_of": "1",
        }
        if prompt:
            data["prompt"] = prompt

        duration_s = len(audio_data) / self.settings.audio.sample_rate
        logger.debug("Enviando audio a whisper-server. Duración: %.2fs, es_parcial: %s", duration_s, is_partial)

        try:
            response = requests.post(
                f"{self.settings.paths.server_url}/inference",
                files=files,
                data=data,
                timeout=self.settings.asr.request_timeout,
            )
            if response.status_code != 200:
                logger.warning(
                    "whisper-server respondió con status=%s, contenido=%s",
                    response.status_code,
                    response.text[:200],
                )
                return AsrResult.failure(
                    AsrFailureKind.SERVER_ERROR,
                    retryable=True,
                    fallback_allowed=False,
                    user_message=f"Whisper local respondió con error HTTP {response.status_code}.",
                    details={"status_code": str(response.status_code)},
                )

            try:
                payload = response.json()
                raw_text = payload.get("text", "")
            except (AttributeError, ValueError) as exc:
                return AsrResult.failure(
                    AsrFailureKind.INVALID_RESPONSE,
                    retryable=False,
                    fallback_allowed=False,
                    user_message="Whisper local devolvió una respuesta inválida.",
                    details={"error": str(exc)},
                )
            return self._postprocess_raw_text(raw_text, audio_data, is_partial=is_partial)

        except requests.exceptions.Timeout:
            logger.warning("Timeout comunicando con whisper-server")
            return AsrResult.failure(
                AsrFailureKind.TIMEOUT,
                retryable=True,
                fallback_allowed=False,
                user_message="Timeout comunicando con Whisper local.",
            )
        except requests.exceptions.RequestException as exc:
            logger.warning("Fallo comunicando con whisper-server: %s", exc)
            return AsrResult.failure(
                AsrFailureKind.NETWORK_ERROR,
                retryable=True,
                fallback_allowed=False,
                user_message="Fallo comunicando con Whisper local.",
                details={"error": str(exc)},
            )

    def warmup(self) -> None:
        silence_samples = int(self.settings.audio.sample_rate * (self.settings.asr.warmup_audio_ms / 1000.0))
        silence = np.zeros(silence_samples, dtype=np.float32)
        try:
            self.transcribe(silence, prompt="", is_partial=True)
        except Exception:
            logger.exception("Warmup de ASR local falló")


class GroqWhisperClient(BaseAsrClient):
    def __init__(self, settings: Settings, runtime: AppRuntime):
        super().__init__(settings, runtime)
        self._client = None
        self._client_lock = threading.Lock()

    def _get_client(self):
        api_key = self.settings.api_keys.groq
        if not api_key:
            return None

        with self._client_lock:
            if self._client is not None:
                return self._client

            try:
                from groq import Groq
            except ImportError:
                logger.warning("El paquete groq no está instalado")
                return None

            self._client = Groq(api_key=api_key)
            return self._client

    def _log_timing(
        self,
        *,
        result: AsrResult,
        wav_elapsed: float,
        client_elapsed: float,
        http_elapsed: float,
        postprocess_elapsed: float,
        started_at: float,
    ) -> None:
        total_elapsed = time.perf_counter() - started_at
        if result.ok:
            logger.info(
                "Groq ASR timing wav=%.3fs client=%.3fs http=%.3fs postprocess=%.3fs total=%.3fs",
                wav_elapsed,
                client_elapsed,
                http_elapsed,
                postprocess_elapsed,
                total_elapsed,
            )
            return

        logger.info(
            "Groq ASR timing failed kind=%s wav=%.3fs client=%.3fs http=%.3fs postprocess=%.3fs total=%.3fs",
            result.failure_kind.value if result.failure_kind else "UNKNOWN",
            wav_elapsed,
            client_elapsed,
            http_elapsed,
            postprocess_elapsed,
            total_elapsed,
        )

    def _sdk_not_installed_result(self) -> AsrResult:
        return AsrResult.failure(
            AsrFailureKind.SDK_NOT_INSTALLED,
            retryable=False,
            fallback_allowed=True,
            user_message="El paquete groq no está instalado.",
        )

    def prewarm_local(self) -> bool:
        if not self.settings.api_keys.groq:
            logger.info("Groq ASR local prewarm omitido: GROQ_API_KEY no configurada")
            return False

        started_at = time.perf_counter()
        client_elapsed = 0.0
        wav_elapsed = 0.0

        try:
            client_started = time.perf_counter()
            client = self._get_client()
            client_elapsed = time.perf_counter() - client_started
            if client is None:
                logger.info("Groq ASR local prewarm omitido: cliente no disponible")
                return False

            if self.settings.groq_asr.prewarm_wav_encoder:
                wav_started = time.perf_counter()
                duration_ms = max(1, min(int(self.settings.groq_asr.prewarm_audio_ms), 1000))
                samples = max(1, int(16000 * duration_ms / 1000))
                audio = np.zeros(samples, dtype=np.float32)
                _ = self.audio_to_wav_bytes(audio)
                wav_elapsed = time.perf_counter() - wav_started

            total_elapsed = time.perf_counter() - started_at
            logger.info(
                "Groq ASR local prewarm completado client=%.3fs wav=%.3fs total=%.3fs",
                client_elapsed,
                wav_elapsed,
                total_elapsed,
            )
            return True
        except Exception:
            logger.debug("Groq ASR local prewarm falló", exc_info=True)
            return False

    def _extract_text(self, transcription) -> str:
        text = getattr(transcription, "text", None)
        if text is not None:
            return str(text)

        if isinstance(transcription, dict):
            return str(transcription.get("text", ""))

        model_dump = getattr(transcription, "model_dump", None)
        if callable(model_dump):
            data = model_dump()
            if isinstance(data, dict):
                return str(data.get("text", ""))

        return ""

    def _validated_model(self) -> str:
        model = self.settings.groq_asr.model
        if isinstance(model, GroqAsrModel):
            return model.value

        model_str = str(model)
        allowed = {item.value for item in self.settings.groq_asr.supported_models}
        if model_str not in allowed:
            fallback = GroqAsrModel.WHISPER_LARGE_V3_TURBO.value
            logger.warning("Modelo Groq ASR no permitido: %s. Usando %s", model_str, fallback)
            return fallback
        return model_str

    def _failure_from_groq_exception(self, exc: Exception) -> AsrResult:
        status_code = getattr(exc, "status_code", None)
        if status_code is None:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)

        details = {"error": str(exc)}
        if status_code is not None:
            details["status_code"] = str(status_code)

        if status_code in (401, 403):
            return AsrResult.failure(
                AsrFailureKind.AUTH_ERROR,
                retryable=False,
                fallback_allowed=True,
                user_message="Groq ASR rechazó la API key o permisos.",
                details=details,
            )
        if status_code == 408:
            return AsrResult.failure(
                AsrFailureKind.TIMEOUT,
                retryable=True,
                fallback_allowed=True,
                user_message="Timeout comunicando con Groq ASR.",
                details=details,
            )
        if status_code == 413:
            return AsrResult.failure(
                AsrFailureKind.PAYLOAD_TOO_LARGE,
                retryable=False,
                fallback_allowed=True,
                user_message="Audio demasiado grande para Groq ASR.",
                details=details,
            )
        if status_code == 429:
            return AsrResult.failure(
                AsrFailureKind.RATE_LIMIT,
                retryable=True,
                fallback_allowed=True,
                user_message="Groq ASR respondió rate limit.",
                details=details,
            )
        if isinstance(status_code, int) and 500 <= status_code <= 599:
            return AsrResult.failure(
                AsrFailureKind.SERVER_ERROR,
                retryable=True,
                fallback_allowed=True,
                user_message="Groq ASR respondió con error del servidor.",
                details=details,
            )

        exc_name = exc.__class__.__name__
        if "Timeout" in exc_name:
            return AsrResult.failure(
                AsrFailureKind.TIMEOUT,
                retryable=True,
                fallback_allowed=True,
                user_message="Timeout comunicando con Groq ASR.",
                details=details,
            )
        if "Connection" in exc_name or "APIConnection" in exc_name:
            return AsrResult.failure(
                AsrFailureKind.NETWORK_ERROR,
                retryable=True,
                fallback_allowed=True,
                user_message="Fallo de red comunicando con Groq ASR.",
                details=details,
            )
        return AsrResult.failure(
            AsrFailureKind.UNKNOWN,
            retryable=False,
            fallback_allowed=True,
            user_message="Fallo desconocido comunicando con Groq ASR.",
            details=details,
        )

    def transcribe(self, audio_data: np.ndarray, prompt: str = "", is_partial: bool = False) -> AsrResult:
        started_at = time.perf_counter()
        wav_elapsed = 0.0
        client_elapsed = 0.0
        http_elapsed = 0.0
        postprocess_elapsed = 0.0

        client_started = time.perf_counter()
        client = self._get_client()
        client_elapsed = time.perf_counter() - client_started

        if client is None and not self.settings.api_keys.groq:
            logger.warning("GROQ_API_KEY no configurada para transcripción ASR online.")
            result = AsrResult.failure(
                AsrFailureKind.MISSING_API_KEY,
                retryable=False,
                fallback_allowed=True,
                user_message="GROQ_API_KEY no configurada en .env.",
            )
            self.runtime.push_text(result.user_message)
            self._log_timing(
                result=result,
                wav_elapsed=wav_elapsed,
                client_elapsed=client_elapsed,
                http_elapsed=http_elapsed,
                postprocess_elapsed=postprocess_elapsed,
                started_at=started_at,
            )
            return result
        if client is None:
            result = self._sdk_not_installed_result()
            self.runtime.push_text(result.user_message)
            self._log_timing(
                result=result,
                wav_elapsed=wav_elapsed,
                client_elapsed=client_elapsed,
                http_elapsed=http_elapsed,
                postprocess_elapsed=postprocess_elapsed,
                started_at=started_at,
            )
            return result

        wav_started = time.perf_counter()
        wav_io = self.audio_to_wav_bytes(audio_data)
        wav_bytes = wav_io.getvalue()
        wav_elapsed = time.perf_counter() - wav_started
        max_bytes = int(self.settings.groq_asr.max_upload_mb * 1024 * 1024)
        if len(wav_bytes) > max_bytes:
            mb = len(wav_bytes) / (1024 * 1024)
            logger.warning("Audio demasiado grande para Groq ASR: %.2fMB > %.2fMB", mb, self.settings.groq_asr.max_upload_mb)
            result = AsrResult.failure(
                AsrFailureKind.PAYLOAD_TOO_LARGE,
                retryable=False,
                fallback_allowed=True,
                user_message=f"Audio demasiado grande para Groq ASR: {mb:.1f}MB > {self.settings.groq_asr.max_upload_mb:.1f}MB.",
                details={"size_mb": f"{mb:.2f}", "max_upload_mb": f"{self.settings.groq_asr.max_upload_mb:.2f}"},
            )
            self.runtime.push_text(result.user_message)
            self._log_timing(
                result=result,
                wav_elapsed=wav_elapsed,
                client_elapsed=client_elapsed,
                http_elapsed=http_elapsed,
                postprocess_elapsed=postprocess_elapsed,
                started_at=started_at,
            )
            return result

        kwargs = {
            "file": ("dictado.wav", wav_bytes),
            "model": self._validated_model(),
            "temperature": float(self.settings.asr.temperature),
            "response_format": self.settings.groq_asr.response_format,
        }

        language = (self.settings.asr.language or "").strip()
        if language and language.lower() != "auto":
            kwargs["language"] = language
        if prompt:
            kwargs["prompt"] = prompt

        duration_s = len(audio_data) / self.settings.audio.sample_rate
        logger.debug(
            "Enviando audio a Groq ASR. Duración: %.2fs, bytes=%d, modelo=%s, es_parcial=%s",
            duration_s,
            len(wav_bytes),
            kwargs["model"],
            is_partial,
        )

        try:
            http_started = time.perf_counter()
            transcription = client.audio.transcriptions.create(**kwargs)
            http_elapsed = time.perf_counter() - http_started
            raw_text = self._extract_text(transcription)
            postprocess_started = time.perf_counter()
            result = self._postprocess_raw_text(raw_text, audio_data, is_partial=is_partial)
            postprocess_elapsed = time.perf_counter() - postprocess_started
            self._log_timing(
                result=result,
                wav_elapsed=wav_elapsed,
                client_elapsed=client_elapsed,
                http_elapsed=http_elapsed,
                postprocess_elapsed=postprocess_elapsed,
                started_at=started_at,
            )
            return result
        except Exception as exc:
            if "http_started" in locals() and http_elapsed == 0.0:
                http_elapsed = time.perf_counter() - http_started
            result = self._failure_from_groq_exception(exc)
            logger.warning("Fallo comunicando con Groq ASR: %s", exc)
            self.runtime.push_text(result.user_message)
            self._log_timing(
                result=result,
                wav_elapsed=wav_elapsed,
                client_elapsed=client_elapsed,
                http_elapsed=http_elapsed,
                postprocess_elapsed=postprocess_elapsed,
                started_at=started_at,
            )
            return result

    def warmup(self) -> None:
        # En modo online el warmup se omite para conservar arranque instantáneo.
        return None


class AsrClientRouter:
    def __init__(
        self,
        settings: Settings,
        runtime: AppRuntime,
        ensure_local_ready: Callable[[], bool] | None = None,
    ):
        self.settings = settings
        self.runtime = runtime
        self._lock = threading.RLock()
        self._ensure_local_ready = ensure_local_ready
        self._local_fallback_client: AsrClient | None = None
        self._prewarm_lock = threading.Lock()
        self._prewarm_in_progress = False
        self._client: AsrClient = self._build_client()

    def _build_client(self) -> AsrClient:
        if self.settings.asr.provider == AsrProvider.GROQ_API:
            return GroqWhisperClient(self.settings, self.runtime)
        return WhisperCppClient(self.settings, self.runtime)

    def _build_local_fallback_client(self) -> AsrClient:
        return WhisperCppClient(self.settings, self.runtime)

    def refresh(self) -> None:
        with self._lock:
            self._client = self._build_client()
            self._local_fallback_client = None

    def _should_try_local_fallback(self, result: AsrResult) -> bool:
        return (
            self.settings.asr.provider == AsrProvider.GROQ_API
            and self.settings.groq_asr.fallback_to_local
            and result.fallback_allowed
        )

    def _get_local_fallback_client(self) -> AsrClient:
        with self._lock:
            if self._local_fallback_client is None:
                self._local_fallback_client = self._build_local_fallback_client()
            return self._local_fallback_client

    def prewarm_async(self) -> bool:
        if self.settings.asr.provider != AsrProvider.GROQ_API:
            return False
        if not self.settings.groq_asr.prewarm_enabled:
            return False

        with self._prewarm_lock:
            if self._prewarm_in_progress:
                return False
            self._prewarm_in_progress = True

        with self._lock:
            client = self._client

        def run() -> None:
            started = time.perf_counter()
            try:
                logger.info("Groq ASR local prewarm async iniciado")
                prewarm = getattr(client, "prewarm_local", None)
                ok = prewarm() if callable(prewarm) else False
                logger.info(
                    "Groq ASR local prewarm async finalizado ok=%s elapsed=%.3fs",
                    ok,
                    time.perf_counter() - started,
                )
            except Exception:
                logger.exception("Groq ASR local prewarm async falló")
            finally:
                with self._prewarm_lock:
                    self._prewarm_in_progress = False

        threading.Thread(target=run, name="GroqAsrLocalPrewarm", daemon=True).start()
        return True

    @property
    def active_name(self) -> str:
        if self.settings.asr.provider == AsrProvider.GROQ_API:
            return f"Groq API · {self.settings.groq_asr.model.value if isinstance(self.settings.groq_asr.model, GroqAsrModel) else self.settings.groq_asr.model}"
        return f"Whisper local · {self.settings.asr.device.value}"

    def transcribe(self, audio_data: np.ndarray, prompt: str = "", is_partial: bool = False) -> AsrResult:
        with self._lock:
            client = self._client

        primary_result = client.transcribe(audio_data, prompt=prompt, is_partial=is_partial)
        if self.settings.asr.provider != AsrProvider.GROQ_API:
            return primary_result
        if primary_result.ok:
            return primary_result
        if not self._should_try_local_fallback(primary_result):
            return primary_result
        if self._ensure_local_ready is None:
            self.runtime.push_text("Fallback local no configurado; se conserva el fallo de Groq ASR.")
            return primary_result

        try:
            local_ready = self._ensure_local_ready()
        except Exception as exc:
            logger.exception("ensure_local_ready falló durante fallback ASR")
            self.runtime.push_text(f"No se pudo preparar Whisper local como fallback: {exc}")
            return primary_result

        if not local_ready:
            self.runtime.push_text("Whisper local no está disponible para fallback; se conserva el fallo de Groq ASR.")
            return primary_result

        local_client = self._get_local_fallback_client()
        self.runtime.push_text("Groq ASR falló; intentando transcripción con Whisper local...")
        local_result = local_client.transcribe(audio_data, prompt=prompt, is_partial=is_partial)
        if local_result.ok:
            self.runtime.push_text("Transcripción recuperada con Whisper local.")
            return local_result

        self.runtime.push_text("Groq ASR falló y Whisper local también falló.")
        return local_result

    def warmup(self) -> None:
        with self._lock:
            client = self._client
        client.warmup()
