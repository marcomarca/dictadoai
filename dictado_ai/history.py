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

    def delete_entry(self, entry_id: str) -> bool:
        """Elimina una entrada por su ID."""
        if not self.history_file.exists():
            return False

        with self._lock:
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                new_lines = []
                deleted = False
                for line in lines:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        data = json.loads(line_str)
                        if data.get("id") == entry_id:
                            deleted = True
                            continue
                    except Exception:
                        pass
                    new_lines.append(line)

                if deleted:
                    with open(self.history_file, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                return deleted
            except Exception as e:
                logger.error("Error al eliminar entrada del historial: %s", e)
                return False

    def get_weekly_metrics(self) -> dict[str, Any]:
        """Calcula las métricas de productividad de los últimos 7 días."""
        if not self.history_file.exists():
            return {
                "avg_wpm": 0,
                "total_words": 0,
                "total_dictations": 0,
                "minutes_saved": 0.0,
            }

        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)

        entries = self.get_recent(1000)
        recent_entries: list[HistoryEntry] = []

        for e in entries:
            try:
                dt = datetime.fromisoformat(e.timestamp)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= seven_days_ago:
                    recent_entries.append(e)
            except Exception:
                recent_entries.append(e)

        if not recent_entries:
            return {
                "avg_wpm": 0,
                "total_words": 0,
                "total_dictations": 0,
                "minutes_saved": 0.0,
            }

        total_words = sum(e.word_count for e in recent_entries)
        valid_wpms = [e.wpm for e in recent_entries if 10 <= e.wpm <= 500]
        avg_wpm = round(sum(valid_wpms) / len(valid_wpms)) if valid_wpms else 0

        # Estimación de tiempo ahorrado: promedio de escritura manual = 40 WPM
        time_typing_sec = (total_words / 40.0) * 60.0
        time_speaking_sec = sum(e.duration_sec for e in recent_entries)
        time_saved_sec = max(0.0, time_typing_sec - time_speaking_sec)
        minutes_saved = round(time_saved_sec / 60.0, 1)

        return {
            "avg_wpm": avg_wpm,
            "total_words": total_words,
            "total_dictations": len(recent_entries),
            "minutes_saved": minutes_saved,
        }

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
