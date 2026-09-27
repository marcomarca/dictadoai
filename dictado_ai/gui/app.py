from __future__ import annotations

import queue
import logging
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from ..audio_devices import list_input_devices, refresh_audio_devices
from ..config import Settings
from ..history import HistoryManager
from ..modes import ModesManager
from ..runtime import AppRuntime
from ..ui_messages import UiMessage
from ..vocabulary import VocabularyManager
from .overlay import DictationOverlay
from .tray import TrayController
from .web_window import SuperWhisperWindow

logger = logging.getLogger(__name__)

WM_DEVICECHANGE = 0x0219


class WindowsDeviceChangeFilter(QAbstractNativeEventFilter, QObject):
    device_changed = Signal()

    def __init__(self, parent: QObject | None = None):
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(600)
        self._debounce_timer.timeout.connect(self._on_debounced_change)

    def nativeEventFilter(self, eventType, message) -> tuple[bool, int]:
        try:
            if eventType in (b"windows_generic_MSG", b"windows_dispatcher_MSG", "windows_generic_MSG", "windows_dispatcher_MSG"):
                msg_addr = int(message)
                if msg_addr:
                    import ctypes.wintypes
                    msg = ctypes.wintypes.MSG.from_address(msg_addr)
                    if msg.message == WM_DEVICECHANGE:
                        self._debounce_timer.start()
        except Exception:
            pass
        return False, 0

    def _on_debounced_change(self) -> None:
        logger.info("Cambio de dispositivo detectado (WM_DEVICECHANGE). Actualizando audio...")
        self.device_changed.emit()


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
        self.vocabulary_manager = VocabularyManager(self.settings.paths.vocabulary_file)
        self.modes_manager = ModesManager(self.settings.paths.modes_file)
        self.overlay = DictationOverlay(settings, is_listening_supplier=self.runtime.state.is_listening)
        
        self.superwhisper_window = SuperWhisperWindow(
            settings,
            self.history_manager,
            toggle_dictation_cb=toggle_callback,
            change_device_cb=change_input_device_callback,
            style_changed_cb=self.overlay.update_style,
            vocabulary_manager=self.vocabulary_manager,
            modes_manager=self.modes_manager,
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

        if sys.platform.startswith("win"):
            self.device_filter = WindowsDeviceChangeFilter(self.app)
            self.device_filter.device_changed.connect(self.on_device_hotplug)
            self.app.installNativeEventFilter(self.device_filter)

        self.poll_timer = QTimer()
        self.poll_timer.timeout.connect(self.process_ui_queue)
        self.poll_timer.start(40)

    def on_device_hotplug(self) -> None:
        try:
            if not self.runtime.state.is_listening():
                refresh_audio_devices()

            if hasattr(self, "superwhisper_window"):
                self.superwhisper_window.bridge.notifyDeviceListChanged()

            selected_key = self.settings.audio.input_device_key
            if selected_key is not None:
                devices = list_input_devices(force_refresh=False)
                device_keys = {d.key for d in devices}
                if selected_key in device_keys:
                    logger.info("Micrófono configurado disponible tras cambio de hardware: %s", selected_key)
                    self.runtime.audio_reconnect_event.set()
                else:
                    logger.warning(
                        "Micrófono configurado desconectado: %s. Reasignando automáticamente a Sistema predeterminado.",
                        selected_key,
                    )
                    from dataclasses import replace
                    self.settings.audio = replace(
                        self.settings.audio,
                        input_device_key=None,
                        input_device_label="Sistema predeterminado",
                    )
                    self.settings.save()
                    self.runtime.audio_reconnect_event.set()
                    self.runtime.push_status("[ MICRÓFONO REASIGNADO ]", self.settings.ui.color_busy)
                    self.runtime.push_text("Micrófono desconectado. Se reasignó al micrófono predeterminado.")
                    if hasattr(self, "tray"):
                        self.tray.rebuild_microphone_menu()
            else:
                # Dispositivo predeterminado del sistema
                self.runtime.audio_reconnect_event.set()
        except Exception as e:
            logger.error("Error procesando evento de cambio de dispositivo de audio: %s", e)


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
