from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import os
import sys
from urllib.parse import urlparse
from dotenv import load_dotenv


class LlmProvider(str, Enum):
    DISABLED = "DESACTIVADO"
    OLLAMA = "OLLAMA"
    GROQ = "GROQ"
    GEMINI = "GEMINI"
    OPENROUTER = "OPENROUTER"


class AsrProvider(str, Enum):
    GROQ_API = "GROQ API (ONLINE)"
    WHISPER_CPP = "WHISPER LOCAL"


class GroqAsrModel(str, Enum):
    WHISPER_LARGE_V3_TURBO = "whisper-large-v3-turbo"
    WHISPER_LARGE_V3 = "whisper-large-v3"


class AsrDevice(str, Enum):
    AUTO = "AUTOMÁTICO"
    GPU = "GPU (NVIDIA)"
    CPU = "CPU"


class DictationMode(str, Enum):
    TOGGLE = "ALTERNAR (CLIC)"
    PUSH_TO_TALK = "MANTENER (PTT)"

@dataclass(frozen=True)
class ApiKeys:
    groq: str = ""
    gemini: str = ""
    openrouter: str = ""

@dataclass(frozen=True)
class PathsConfig:
    project_root: Path
    server_url: str = "http://127.0.0.1:8170"
    server_exe_name: str = "bin/whisper-server.exe"
    model_relative_path: Path = Path("models") / "ggml-large-v3-turbo-q8_0.bin"
    model_download_url: str = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo-q8_0.bin?download=true"
    debug_audio_dir_name: str = "debug_audio"

    @property
    def server_exe_path(self) -> Path:
        return self.project_root / self.server_exe_name

    @property
    def server_port(self) -> int:
        return urlparse(self.server_url).port or 8170

    @property
    def model_path(self) -> Path:
        # Si existe el q8_0, usarlo
        q8 = self.project_root / self.model_relative_path
        if q8.exists():
            return q8
        # Si existe el q5_0 como alternativa previa, usarlo
        q5 = self.project_root / "models" / "ggml-large-v3-turbo-q5_0.bin"
        if q5.exists():
            return q5
        return q8

    @property
    def logs_dir(self) -> Path:
        return self.project_root / "logs"

    @property
    def debug_audio_dir(self) -> Path:
        return self.project_root / self.debug_audio_dir_name


@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    block_size: int = 512
    level_update_interval: float = 0.05
    input_device_key: str | None = None
    input_device_label: str = "Sistema predeterminado"


@dataclass(frozen=True)
class AsrConfig:
    provider: AsrProvider = AsrProvider.GROQ_API
    language: str = "" # "" para detección automática (multilingüe)
    request_timeout: float = 300.0
    max_context_chars: int = 180
    max_context_segments: int = 6
    warmup_audio_ms: int = 1000
    temperature: float = 0.0
    no_context: bool = True
    suppress_nst: bool = True
    split_on_word: bool = True
    no_timestamps: bool = True
    device: AsrDevice = AsrDevice.AUTO
    initial_prompt: str = (
        "Bilingual dictation. Dictado bilingüe. I will speak in English and Spanish. Hablaré en inglés y español."
    )


@dataclass(frozen=True)
class GroqAsrConfig:
    model: GroqAsrModel = GroqAsrModel.WHISPER_LARGE_V3_TURBO
    response_format: str = "verbose_json"
    fallback_to_local: bool = True
    prewarm_enabled: bool = True
    prewarm_wav_encoder: bool = True
    prewarm_audio_ms: int = 200
    # Límite conservador pedido para evitar 413/payload too large antes de llamar a la API.
    max_upload_mb: float = 19.5
    supported_models: tuple[GroqAsrModel, ...] = (
        GroqAsrModel.WHISPER_LARGE_V3_TURBO,
        GroqAsrModel.WHISPER_LARGE_V3,
    )
    supported_formats: tuple[str, ...] = (
        "flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav", "webm"
    )


@dataclass(frozen=True)
class VadConfig:
    enabled: bool = True
    threshold: float = 0.5
    sample_rate: int = 16000
    min_speech_duration_ms: int = 250
    min_wpm_trigger: float = 25.0  # Si el WPM es menor a esto, se activa el VAD
    # Frases que disparan la doble verificación con Silero VAD
    suspicious_patterns: list[str] = field(default_factory=lambda: [
    # Español: subtítulos / créditos / cierre típico
    "música",
    "musica",
    "subtítulos",
    "subtitulos",
    "subtítulo",
    "subtitulo",
    "subtitulado por",
    "subtítulos por",
    "subtitulos por",
    "traducido por",
    "transcrito por",
    "transcripción por",
    "transcripcion por",
    "amara.org",
    "la comunidad de amara.org",
    "gracias por ver",
    "gracias por mirar",
    "gracias por escuchar",
    "gracias por su atención",
    "gracias por su atencion",
    "suscríbete",
    "suscribete",
    "dale like",
    "deja tu like",
    "activa la campanita",
    "nos vemos en el próximo video",
    "nos vemos en el proximo video",
    "hasta la próxima",
    "hasta la proxima",
    "chao",
    "adiós",
    "adios",
    "silencio",
    "ruido de fondo",
    "aplausos",
    "risas",
    "sonido ambiente",
    "música de fondo",
    "musica de fondo",
    "no creo que lo traduzca mal",
    "gracias",

    # Inglés: subtitles / credits
    "subtitles",
    "subtitle",
    "captions",
    "caption",
    "closed captions",
    "cc by",
    "subtitled by",
    "subtitles by",
    "captioned by",
    "captions by",
    "translated by",
    "translation by",
    "transcribed by",
    "transcription by",
    "amara.org",
    "the amara.org community",
    "subtitles by the amara.org community",
    "captioned by the amara.org community",

    # Inglés: cierres típicos de YouTube / videos
    "thanks for watching",
    "thank you for watching",
    "thanks for listening",
    "thank you for listening",
    "thanks for viewing",
    "thank you for viewing",
    "please subscribe",
    "subscribe to my channel",
    "subscribe to our channel",
    "like and subscribe",
    "don't forget to subscribe",
    "dont forget to subscribe",
    "hit the subscribe button",
    "hit the bell",
    "click the bell",
    "turn on notifications",
    "leave a like",
    "smash that like button",
    "see you next time",
    "see you in the next video",
    "see you in the next one",
    "until next time",
    "bye for now",
    "goodbye",
    "thank you",
    "thanks",
    "I will speak in English",

    # Inglés: descripciones no habladas / ruido
    "[music]",
    "(music)",
    "music",
    "background music",
    "intro music",
    "outro music",
    "[applause]",
    "(applause)",
    "applause",
    "[laughter]",
    "(laughter)",
    "laughter",
    "[silence]",
    "(silence)",
    "silence",
    "[noise]",
    "(noise)",
    "noise",
    "background noise",
    "inaudible",
    "unintelligible",
    "foreign language",
    "[foreign language]",
    "(foreign language)",

    # Frases alucinadas comunes en Whisper cuando no hay voz clara
    "you",
    "okay",
    "ok",
    "hello",
    "hi",
    "yeah",
    "yes",
    "no",
    "hmm",
    "um",
    "uh",
    "mmm",
    "bye",
    "bye bye",
    "all right",
    "alright",
    "let's go",
    "welcome back",
    "welcome to my channel",
    "welcome to the channel",
    "this is a test",
])


@dataclass(frozen=True)
class OllamaConfig:
    enabled: bool = True
    url: str = "http://localhost:11434"
    model: str = "gemma2:2b"
    timeout: float = 15.0
    system_prompt: str = (
        "Eres un asistente de transcripción experto. Tu tarea es corregir y formatear el texto de un dictado.\n"
        "REGLAS ESTRICTAS:\n"
        "1. IDIOMA: Dictado BILINGÜE (ES/EN). Corrige ortografía en ambos idiomas sin traducir nada.\n"
        "2. COMANDOS DE VOZ: Convierte comandos a signos de puntuación REALES:\n"
        "   - 'punto', 'punto final' o 'comando punto' -> .\n"
        "   - 'coma' o 'comando coma' -> ,\n"
        "   - 'dos puntos' o 'comando dos puntos' -> :\n"
        "   - 'salto', 'enter' o 'nuevo párrafo' -> \\n\n"
        "   - 'abrir/cerrar pregunta' -> ¿ / ?\n"
        "   - 'abrir/cerrar exclamación' -> ¡ / !\n"
        "3. CONTEXTO: Si 'punto' o 'coma' son parte del discurso (ej: 'el punto de vista'), NO los cambies.\n"
        "4. FORMATO: Responde solo con JSON válido: {\"corrected_text\": \"...\"}\n"
        "5. No expliques nada. No completes frases. No elimines saltos de línea \\n preexistentes."
    )


@dataclass(frozen=True)
class AppConfig:
    app_name: str = "Dictado AI"
    hotkey: str = "ctrl+alt+x"
    server_boot_timeout: float = 45.0
    auto_copy_clipboard: bool = True
    auto_pause_media: bool = True
    media_key_fallback_enabled: bool = True
    dictation_mode: DictationMode = DictationMode.TOGGLE
    typing_speed_wpm: int = 60
    save_debug_audio: bool = False


@dataclass(frozen=True)
class UiTheme:
    popup_width: int = 560
    popup_height: int = 176
    popup_margin_top: int = 20
    popup_margin_right: int = 24
    popup_corner_radius: int = 22
    color_bg: str = "#0B1020"
    color_card: str = "#11192B"
    color_card_alt: str = "#182238"
    color_border: str = "rgba(255,255,255,0.08)"
    color_text_primary: str = "#F8FAFC"
    color_text_secondary: str = "#A7B2C9"
    color_text_muted: str = "#7D89A3"
    color_active: str = "#35D07F"
    color_busy: str = "#F6A53A"
    color_paused: str = "#FF6467"
    color_init: str = "#60A5FA"
    color_level: str = "#5EEAD4"
    color_level_bg: str = "rgba(255,255,255,0.08)"


@dataclass
class Settings:
    paths: PathsConfig
    audio: AudioConfig = field(default_factory=AudioConfig)
    asr: AsrConfig = field(default_factory=AsrConfig)
    groq_asr: GroqAsrConfig = field(default_factory=GroqAsrConfig)
    vad: VadConfig = field(default_factory=VadConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    app: AppConfig = field(default_factory=AppConfig)
    ui: UiTheme = field(default_factory=UiTheme)
    active_provider: LlmProvider = LlmProvider.DISABLED
    api_keys: ApiKeys = field(default_factory=ApiKeys)

    @classmethod
    def default(cls) -> "Settings":
        if getattr(sys, "frozen", False):
            project_root = Path(sys.executable).resolve().parent
        else:
            package_dir = Path(__file__).resolve().parent
            project_root = package_dir.parent
        
        load_dotenv(project_root / ".env")
        
        return cls(
            paths=PathsConfig(project_root=project_root),
            api_keys=ApiKeys(
                groq=os.getenv("GROQ_API_KEY", ""),
                gemini=os.getenv("GEMINI_API_KEY", ""),
                openrouter=os.getenv("OPENROUTER_API_KEY", ""),
            )
        )
