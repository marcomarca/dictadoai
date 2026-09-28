from __future__ import annotations

import queue
import re
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .config import Settings
from .ui_messages import UiMessage


class RuntimeState:
    def __init__(self, max_context_segments: int):
        self._lock = threading.Lock()
        self._is_listening = False
        self._is_processing = False
        self._current_live_utterance_id: Optional[int] = None
        self._utterance_counter = 0
        self._context_history: deque[str] = deque(maxlen=max_context_segments)
        self._last_text_ended_sentence = True

    def is_listening(self) -> bool:
        with self._lock:
            return self._is_listening

    def set_is_listening(self, value: bool) -> None:
        with self._lock:
            self._is_listening = value

    def is_processing(self) -> bool:
        with self._lock:
            return self._is_processing

    def set_is_processing(self, value: bool) -> None:
        with self._lock:
            self._is_processing = value

    def toggle_listening(self) -> bool:
        with self._lock:
            self._is_listening = not self._is_listening
            return self._is_listening

    def set_live_utterance_id(self, value: Optional[int]) -> None:
        with self._lock:
            self._current_live_utterance_id = value

    def get_live_utterance_id(self) -> Optional[int]:
        with self._lock:
            return self._current_live_utterance_id

    def next_utterance_id(self) -> int:
        with self._lock:
            self._utterance_counter += 1
            return self._utterance_counter

    def build_context_prompt(self, max_chars: int) -> str:
        with self._lock:
            history = list(self._context_history)

        if not history:
            return ""

        prompt = " ".join(history).strip()
        if len(prompt) <= max_chars:
            return prompt
        return prompt[-max_chars:].lstrip()

    def register_confirmed_text(self, text: str) -> None:
        ended_sentence = bool(re.search(r"[.!?:;…]$", text))
        with self._lock:
            self._context_history.append(text)
            self._last_text_ended_sentence = ended_sentence

    def last_text_ended_sentence(self) -> bool:
        with self._lock:
            return self._last_text_ended_sentence


@dataclass
class AppRuntime:
    settings: Settings
    state: RuntimeState = field(init=False)
    final_queue: "queue.Queue[dict]" = field(default_factory=queue.Queue)
    ui_queue: "queue.Queue[UiMessage]" = field(default_factory=queue.Queue)
    stop_event: threading.Event = field(default_factory=threading.Event)
    listen_event: threading.Event = field(default_factory=threading.Event)
    audio_reconnect_event: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        self.state = RuntimeState(max_context_segments=self.settings.asr.max_context_segments)

    def push_status(self, text: str, color: str) -> None:
        self.ui_queue.put(UiMessage(kind="status", text=text, color=color))

    def push_text(self, text: str) -> None:
        self.ui_queue.put(UiMessage(kind="text", text=text))

    def push_draft(self, text: str) -> None:
        self.ui_queue.put(UiMessage(kind="draft", text=text))

    def push_level(self, level: float) -> None:
        clamped = max(0.0, min(1.0, float(level)))
        self.ui_queue.put(UiMessage(kind="level", level=clamped))

    def push_clipboard(self, text: str) -> None:
        self.ui_queue.put(UiMessage(kind="clipboard", text=text))

    def push_stats(self, wpm: float, time_saved: float) -> None:
        self.ui_queue.put(UiMessage(kind="stats", wpm=wpm, time_saved=time_saved))

    def push_preview(self, duration: float) -> None:
        self.ui_queue.put(UiMessage(kind="preview", duration=duration))

    def show_completed_ui(self) -> None:
        self.push_status("[ LISTO ]", self.settings.ui.color_active)
        self.push_draft("")
        self.push_level(0.0)

    def show_paused_ui(self) -> None:
        self.push_status("[ PAUSADO ]", self.settings.ui.color_paused)
        self.push_text(f"Presiona {self.settings.app.hotkey} o usa el tray icon para iniciar")
        self.push_draft("")
        self.push_level(0.0)

    def show_active_idle_ui(self) -> None:
        self.push_status("[ GRABANDO ]", self.settings.ui.color_active)
        self.push_text("Habla ahora...")
        self.push_draft("")
