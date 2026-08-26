from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UiMessage:
    kind: str
    text: str = ""
    color: str = ""
    level: float = 0.0
    wpm: float = 0.0
    time_saved: float = 0.0
    duration: float = 0.0
