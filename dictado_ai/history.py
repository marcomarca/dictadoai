from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class HistoryEntry:
    id: str
    timestamp: str
    text: str
    raw_asr: str = ""
    word_count: int = 0
    duration_sec: float = 0.0
    wpm: float = 0.0
    paste_success: bool = True
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryEntry:
        return cls(
            id=data.get("id", ""),
            timestamp=data.get("timestamp", ""),
            text=data.get("text", ""),
            raw_asr=data.get("raw_asr", ""),
            word_count=int(data.get("word_count", 0)),
            duration_sec=float(data.get("duration_sec", 0.0)),
            wpm=float(data.get("wpm", 0.0)),
            paste_success=bool(data.get("paste_success", True)),
            provider=data.get("provider", ""),
        )


class HistoryManager:
    """Maneja la persistencia append-only thread-safe del historial de transcripciones en JSONL."""

    def __init__(self, history_file: Path):
        self.history_file = Path(history_file)
        self._lock = threading.Lock()
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning("No se pudo crear directorio para historial: %s", e)

    def append_entry(self, entry: HistoryEntry) -> bool:
        """Agrega de forma atómica y segura una entrada al final del archivo de historial."""
        with self._lock:
            try:
                self._ensure_dir()
                line = json.dumps(entry.to_dict(), ensure_ascii=False)
                with open(self.history_file, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
                logger.debug("Entrada de historial guardada: id=%s text='%s'", entry.id, entry.text[:40])
                return True
            except Exception as e:
                logger.error("Error al guardar entrada en historial: %s", e)
                return False

    def get_recent(self, limit: int = 50) -> list[HistoryEntry]:
        """Obtiene las entradas más recientes en orden cronológico inverso (la más nueva primero)."""
        if not self.history_file.exists():
            return []

        with self._lock:
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                entries: list[HistoryEntry] = []
                for line in reversed(lines):
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        data = json.loads(line_str)
                        entries.append(HistoryEntry.from_dict(data))
                        if len(entries) >= limit:
                            break
                    except Exception:
                        continue
                return entries
            except Exception as e:
                logger.error("Error al leer historial: %s", e)
                return []

    def clear(self) -> bool:
        """Limpia todo el historial (útil para pruebas o reseteo)."""
        with self._lock:
            try:
                if self.history_file.exists():
                    self.history_file.unlink()
                return True
            except Exception as e:
                logger.error("Error al limpiar historial: %s", e)
                return False
