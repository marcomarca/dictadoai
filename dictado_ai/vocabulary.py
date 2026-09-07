from __future__ import annotations

import json
import logging
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VocabularyEntry:
    id: str
    word: str
    replacement: str = ""
    enabled: bool = True
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VocabularyEntry:
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            word=data.get("word", "").strip(),
            replacement=data.get("replacement", "").strip(),
            enabled=bool(data.get("enabled", True)),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
        )


class VocabularyManager:
    """Maneja el vocabulario y las reglas de sustitución determinista y contextual."""

    def __init__(self, vocab_file: Path):
        self.vocab_file = Path(vocab_file)
        self._lock = threading.Lock()
        self._ensure_file()

    def _ensure_file(self) -> None:
        try:
            self.vocab_file.parent.mkdir(parents=True, exist_ok=True)
            if not self.vocab_file.exists():
                with open(self.vocab_file, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("No se pudo inicializar archivo de vocabulario: %s", e)

    def _load_locked(self) -> list[VocabularyEntry]:
        if not self.vocab_file.exists():
            return []
        try:
            with open(self.vocab_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [VocabularyEntry.from_dict(item) for item in data if isinstance(item, dict)]
            return []
        except Exception as e:
            logger.error("Error al cargar vocabulario: %s", e)
            return []

    def _save_locked(self, entries: list[VocabularyEntry]) -> bool:
        try:
            self.vocab_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.vocab_file, "w", encoding="utf-8") as f:
                json.dump([e.to_dict() for e in entries], f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error("Error al guardar vocabulario: %s", e)
            return False

    def get_all(self) -> list[VocabularyEntry]:
        with self._lock:
            return self._load_locked()

    def add_item(self, word: str, replacement: str = "") -> VocabularyEntry | None:
        clean_word = word.strip()
        if not clean_word:
            return None

        clean_replacement = replacement.strip()

        with self._lock:
            entries = self._load_locked()
            # Si ya existe exactamente la misma palabra, actualizar reemplazo
            for entry in entries:
                if entry.word.lower() == clean_word.lower():
                    entry.replacement = clean_replacement
                    entry.enabled = True
                    self._save_locked(entries)
                    return entry

            new_entry = VocabularyEntry(
                id=str(uuid.uuid4())[:8],
                word=clean_word,
                replacement=clean_replacement,
                enabled=True,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            entries.append(new_entry)
            self._save_locked(entries)
            logger.info("Término de vocabulario añadido: '%s' -> '%s'", clean_word, clean_replacement)
            return new_entry

    def delete_item(self, item_id: str) -> bool:
        with self._lock:
            entries = self._load_locked()
            new_entries = [e for e in entries if e.id != item_id]
            if len(new_entries) != len(entries):
                self._save_locked(new_entries)
                logger.info("Término de vocabulario eliminado id=%s", item_id)
                return True
            return False

    def toggle_item(self, item_id: str) -> bool:
        with self._lock:
            entries = self._load_locked()
            for entry in entries:
                if entry.id == item_id:
                    entry.enabled = not entry.enabled
                    self._save_locked(entries)
                    return True
            return False

    def apply_replacements(self, text: str) -> str:
        """Aplica sustituciones directas sobre el texto en base a las reglas habilitadas."""
        if not text:
            return text

        entries = self.get_all()
        result = text

        for entry in entries:
            if not entry.enabled or not entry.replacement:
                continue

            pattern = re.compile(rf"\b{re.escape(entry.word)}\b", re.IGNORECASE)
            result = pattern.sub(entry.replacement, result)

        return result

    def get_prompt_hints(self) -> list[str]:
        """Obtiene la lista de palabras clave para enriquecer el prompt del LLM."""
        entries = self.get_all()
        hints: list[str] = []
        for entry in entries:
            if not entry.enabled:
                continue
            if entry.replacement:
                hints.append(f"{entry.word} (reemplazar por '{entry.replacement}')")
            else:
                hints.append(entry.word)
        return hints
