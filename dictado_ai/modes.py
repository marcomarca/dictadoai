from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DictationModeConfig:
    id: str
    name: str
    description: str
    system_prompt: str = ""
    is_raw: bool = False
    temperature: float = 0.0
    is_default: bool = False
    active: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DictationModeConfig:
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            name=data.get("name", "Modo"),
            description=data.get("description", ""),
            system_prompt=data.get("system_prompt", ""),
            is_raw=bool(data.get("is_raw", False)),
            temperature=float(data.get("temperature", 0.0)),
            is_default=bool(data.get("is_default", False)),
            active=bool(data.get("active", False)),
        )


DEFAULT_MODES: list[dict[str, Any]] = [
    {
        "id": "default",
        "name": "Default",
        "description": "Dictado general con puntuación y gramática fluida en español.",
        "system_prompt": "Eres un corrector de transcripciones por voz en español. Corrige ortografía, puntuación, mayúsculas y acentos. No agregues comentarios, saludos ni explicaciones. Devuelve únicamente el texto corregido.",
        "is_raw": False,
        "temperature": 0.0,
        "is_default": True,
        "active": True,
    },
    {
        "id": "code",
        "name": "Programación / Código",
        "description": "Formatea nombres de funciones, variables (camelCase/snake_case) y términos de desarrollo.",
        "system_prompt": "Eres un asistente de dictado para programadores. Formatea el texto transcrito para código y tecnología. Si el usuario dicta nombres de variables o funciones, formátalos apropiadamente (como camelCase o snake_case según corresponda). Mantén las palabras clave en inglés de programación exactas. Devuelve ÚNICAMENTE el texto final formateado sin explicaciones.",
        "is_raw": False,
        "temperature": 0.0,
        "is_default": False,
        "active": False,
    },
    {
        "id": "email",
        "name": "Correo Profesional",
        "description": "Redacción ejecutiva con párrafos pulidos y tono corporativo impecable.",
        "system_prompt": "Eres un asistente de redacción ejecutiva. Corrige y estructura el dictado con un tono formal y corporativo impecable, buena división de párrafos y puntuación precisa. Devuelve ÚNICAMENTE el texto final sin explicaciones.",
        "is_raw": False,
        "temperature": 0.1,
        "is_default": False,
        "active": False,
    },
    {
        "id": "raw",
        "name": "Raw Whisper (Ultra-Rápido)",
        "description": "Transcripción directa literal de Whisper sin invocar LLM para latencia mínima.",
        "system_prompt": "",
        "is_raw": True,
        "temperature": 0.0,
        "is_default": False,
        "active": False,
    },
]


class ModesManager:
    """Gestiona los modos de dictado y el prompt activo del sistema."""

    def __init__(self, modes_file: Path):
        self.modes_file = Path(modes_file)
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        try:
            self.modes_file.parent.mkdir(parents=True, exist_ok=True)
            if not self.modes_file.exists():
                with open(self.modes_file, "w", encoding="utf-8") as f:
                    json.dump(DEFAULT_MODES, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("No se pudo inicializar archivo de modos: %s", e)

    def _load_locked(self) -> list[DictationModeConfig]:
        if not self.modes_file.exists():
            return [DictationModeConfig.from_dict(m) for m in DEFAULT_MODES]
        try:
            with open(self.modes_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return [DictationModeConfig.from_dict(item) for item in data if isinstance(item, dict)]
            return [DictationModeConfig.from_dict(m) for m in DEFAULT_MODES]
        except Exception as e:
            logger.error("Error al cargar modos: %s", e)
            return [DictationModeConfig.from_dict(m) for m in DEFAULT_MODES]

    def _save_locked(self, modes: list[DictationModeConfig]) -> bool:
        try:
            self.modes_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.modes_file, "w", encoding="utf-8") as f:
                json.dump([m.to_dict() for m in modes], f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error("Error al guardar modos: %s", e)
            return False

    def get_all(self) -> list[DictationModeConfig]:
        with self._lock:
            return self._load_locked()

    def get_active_mode(self) -> DictationModeConfig:
        modes = self.get_all()
        for mode in modes:
            if mode.active:
                return mode
        # Fallback si ninguno estaba activo
        return modes[0] if modes else DictationModeConfig.from_dict(DEFAULT_MODES[0])

    def set_active_mode(self, mode_id: str) -> bool:
        with self._lock:
            modes = self._load_locked()
            found = False
            for mode in modes:
                if mode.id == mode_id:
                    mode.active = True
                    found = True
                else:
                    mode.active = False
            if found:
                self._save_locked(modes)
                logger.info("Modo de dictado activado: %s", mode_id)
                return True
            return False

    def add_mode(
        self,
        name: str,
        description: str,
        system_prompt: str = "",
        is_raw: bool = False,
        temperature: float = 0.0,
    ) -> DictationModeConfig | None:
        clean_name = name.strip()
        if not clean_name:
            return None

        with self._lock:
            modes = self._load_locked()
            new_mode = DictationModeConfig(
                id=str(uuid.uuid4())[:8],
                name=clean_name,
                description=description.strip(),
                system_prompt=system_prompt.strip(),
                is_raw=is_raw,
                temperature=temperature,
                is_default=False,
                active=False,
            )
            modes.append(new_mode)
            self._save_locked(modes)
            logger.info("Nuevo modo de dictado creado: %s (id=%s)", clean_name, new_mode.id)
            return new_mode

    def delete_mode(self, mode_id: str) -> bool:
        with self._lock:
            modes = self._load_locked()
            # No permitir borrar el modo default
            target = next((m for m in modes if m.id == mode_id), None)
            if not target or target.is_default:
                return False

            was_active = target.active
            modes = [m for m in modes if m.id != mode_id]
            if was_active and modes:
                modes[0].active = True

            self._save_locked(modes)
            logger.info("Modo de dictado eliminado: %s", mode_id)
            return True
