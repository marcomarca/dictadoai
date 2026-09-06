from __future__ import annotations

import queue
import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ..config import Settings
from ..history import HistoryManager
from ..runtime import AppRuntime
from ..ui_messages import UiMessage
from .overlay import DictationOverlay
from .tray import TrayController
from .web_window import SuperWhisperWindow

logger = logging.getLogger(__name__)


class DictationQtApp:
    def __init__(
        self,
        app: QApplication,
        settings: Settings,
        runtime: AppRuntime,
        toggle_callback,
        restart_asr_callback,
        change_mode_callback,
        change_input_device_callback,
        download_model_callback=None,
    ):
        self.app = app
        self.settings = settings
        self.runtime = runtime
        self.history_manager = HistoryManager(self.settings.paths.history_file)
        self.overlay = DictationOverlay(settings, is_listening_supplier=self.runtime.state.is_listening)
        
        self.superwhisper_window = SuperWhisperWindow(
            settings,
            self.history_manager,
            toggle_dictation_cb=toggle_callback,
            change_device_cb=change_input_device_callback,
        )

        self.tray = TrayController(
            settings,
            self.overlay,
            is_listening_supplier=self.runtime.state.is_listening,
            toggle_callback=toggle_callback,
            restart_asr_callback=restart_asr_callback,
            change_mode_callback=change_mode_callback,
            change_input_device_callback=change_input_device_callback,
            download_model_callback=download_model_callback,
            open_panel_callback=self.superwhisper_window.show_window,
        )

        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.process_ui_queue)
        self.poll_timer.start(40)

    def process_ui_queue(self) -> None:
        try:
            # Limitar el procesamiento por tick para no bloquear el hilo principal
            # si la cola se llena por alguna razón
            count = 0
            while count < 40:
                try:
                    msg: UiMessage = self.runtime.ui_queue.get_nowait()
                except queue.Empty:
                    break
                
                count += 1
                try:
                    if msg.kind == "status":
                        self.overlay.set_status(msg.text, msg.color)
                        self.tray.update_from_status(msg.text)
                        if hasattr(self, "superwhisper_window"):
                            self.superwhisper_window.bridge.statusChanged.emit(msg.text, msg.color or "")
                    elif msg.kind == "text":
                        self.overlay.set_info(msg.text)
                    elif msg.kind == "draft":
                        self.overlay.set_draft(msg.text)
                    elif msg.kind == "level":
                        self.overlay.set_level(msg.level)
                        if hasattr(self, "superwhisper_window"):
                            self.superwhisper_window.bridge.audioLevelChanged.emit(msg.level)
                    elif msg.kind == "clipboard":
                        # El acceso al portapapeles puede fallar si está bloqueado por otra app
                        try:
                            self.app.clipboard().setText(msg.text)
                        except Exception as e:
                            logger.warning("No se pudo actualizar portapapeles en UI: %s", e)
                        if hasattr(self, "superwhisper_window"):
                            self.superwhisper_window.bridge.notifyHistoryUpdated()
                    elif msg.kind == "stats":
                        self.overlay.set_stats(msg.wpm, msg.time_saved)
                    elif msg.kind == "preview":
                        self.overlay.preview(msg.duration)
                except Exception as e:
                    logger.error("Error procesando mensaje UI tipo %s: %s", msg.kind, e, exc_info=True)

            # Sincronizar visibilidad siempre al final del procesamiento
            self.overlay.sync_visibility()
            
        except Exception as e:
            logger.error("Fallo crítico en poll_timer del hilo principal: %s", e, exc_info=True)
