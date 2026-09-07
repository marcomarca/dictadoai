from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QObject, QPoint, QUrl, Signal, Slot, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMainWindow, QApplication, QWidget, QVBoxLayout
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings

from ..audio_devices import list_input_devices
from ..autostart import is_autostart_enabled, set_autostart
from ..history import HistoryManager
from ..hotkeys import send_paste_command, set_clipboard_text, ClipboardGuard
from ..modes import ModesManager
from ..vocabulary import VocabularyManager
from .theme import get_app_icon

if TYPE_CHECKING:
    from ..config import Settings
    from ..controller import DictationController

logger = logging.getLogger(__name__)


class WebBridge(QObject):
    """Puente de comunicación bidireccional entre Python y JavaScript mediante QWebChannel."""

    # Señales emitidas desde Python hacia el DOM en JavaScript
    historyUpdated = Signal(str)
    statusChanged = Signal(str, str)
    audioLevelChanged = Signal(float)
    deviceListChanged = Signal(str, str)
    configUpdated = Signal(str)

    def __init__(
        self,
        settings: Settings,
        history_manager: HistoryManager,
        window: SuperWhisperWindow,
        toggle_dictation_cb: Callable[[], None] | None = None,
        change_device_cb: Callable[[str | None, str], None] | None = None,
        vocabulary_manager: VocabularyManager | None = None,
        modes_manager: ModesManager | None = None,
    ):
        super().__init__()
        self.settings = settings
        self.history_manager = history_manager
        self.vocabulary_manager = vocabulary_manager or VocabularyManager(settings.paths.vocabulary_file)
        self.modes_manager = modes_manager or ModesManager(settings.paths.modes_file)
        self.window = window
        self.toggle_dictation_cb = toggle_dictation_cb
        self.change_device_cb = change_device_cb

    # --- Slots de Vocabulario ---
    @Slot(result=str)
    def getVocabulary(self) -> str:
        try:
            items = self.vocabulary_manager.get_all()
            return json.dumps([item.to_dict() for item in items], ensure_ascii=False)
        except Exception as e:
            logger.error("Error obteniendo vocabulario: %s", e)
            return "[]"

    @Slot(str, str, result=str)
    def addVocabulary(self, word: str, replacement: str = "") -> str:
        try:
            entry = self.vocabulary_manager.add_item(word, replacement)
            return json.dumps(entry.to_dict() if entry else {}, ensure_ascii=False)
        except Exception as e:
            logger.error("Error agregando vocabulario: %s", e)
            return "{}"

    @Slot(str, result=bool)
    def deleteVocabulary(self, item_id: str) -> bool:
        return self.vocabulary_manager.delete_item(item_id)

    @Slot(str, result=bool)
    def toggleVocabulary(self, item_id: str) -> bool:
        return self.vocabulary_manager.toggle_item(item_id)

    # --- Slots de Modos ---
    @Slot(result=str)
    def getModes(self) -> str:
        try:
            modes = self.modes_manager.get_all()
            return json.dumps([m.to_dict() for m in modes], ensure_ascii=False)
        except Exception as e:
            logger.error("Error obteniendo modos: %s", e)
            return "[]"

    @Slot(str, result=bool)
    def setActiveMode(self, mode_id: str) -> bool:
        return self.modes_manager.set_active_mode(mode_id)

    @Slot(str, str, str, bool, result=str)
    def createMode(self, name: str, description: str, system_prompt: str, is_raw: bool = False) -> str:
        try:
            m = self.modes_manager.add_mode(name, description, system_prompt, is_raw=is_raw)
            return json.dumps(m.to_dict() if m else {}, ensure_ascii=False)
        except Exception as e:
            logger.error("Error creando modo: %s", e)
            return "{}"

    @Slot(str, result=bool)
    def deleteMode(self, mode_id: str) -> bool:
        return self.modes_manager.delete_mode(mode_id)

    # --- Slots de Métricas Dashboard ---
    @Slot(result=str)
    def getDashboardMetrics(self) -> str:
        try:
            metrics = self.history_manager.get_weekly_metrics()
            return json.dumps(metrics, ensure_ascii=False)
        except Exception as e:
            logger.error("Error calculando métricas: %s", e)
            return json.dumps({"avg_wpm": 0, "total_words": 0, "total_dictations": 0, "minutes_saved": 0.0})

    # --- Slots de Historial ---
    @Slot(int, result=str)
    def getHistory(self, limit: int = 100) -> str:
        try:
            entries = self.history_manager.get_recent(limit)
            return json.dumps([e.to_dict() for e in entries], ensure_ascii=False)
        except Exception as e:
            logger.error("Error obteniendo historial para la UI: %s", e)
            return "[]"

    @Slot(str)
    def copyToClipboard(self, text: str) -> None:
        try:
            QApplication.clipboard().setText(text)
        except Exception as e:
            logger.warning("Fallo al copiar desde UI a portapapeles: %s", e)

    @Slot(str)
    def reinjectTranscription(self, text: str) -> None:
        """Minimiza la ventana y pega el texto en el cursor activo."""
        try:
            self.window.hide()
            def _async_paste():
                import time
                time.sleep(0.15)
                with ClipboardGuard(enabled=not self.settings.app.auto_copy_clipboard):
                    set_clipboard_text(text)
                    send_paste_command()
            threading.Thread(target=_async_paste, daemon=True).start()
        except Exception as e:
            logger.error("Error re-inyectando texto: %s", e)

    @Slot(str, result=bool)
    def deleteHistoryItem(self, item_id: str) -> bool:
        ok = self.history_manager.delete_entry(item_id)
        if ok:
            self.notifyHistoryUpdated()
        return ok

    def notifyHistoryUpdated(self) -> None:
        try:
            entries = self.history_manager.get_recent(100)
            self.historyUpdated.emit(json.dumps([e.to_dict() for e in entries], ensure_ascii=False))
        except Exception as e:
            logger.error("Error notificando actualización de historial: %s", e)

    # --- Slots de Dispositivos de Audio ---
    @Slot(result=str)
    def listAudioDevices(self) -> str:
        try:
            devices = list_input_devices()
            devices_data = [{"key": d.key, "label": d.label} for d in devices]
            selected_key = self.settings.audio.input_device_key or ""
            return json.dumps(devices_data, ensure_ascii=False)
        except Exception as e:
            logger.error("Error listando dispositivos de audio: %s", e)
            return "[]"

    @Slot(str, str)
    def setAudioDevice(self, key: str, label: str) -> None:
        try:
            real_key = key if key else None
            if self.change_device_cb:
                self.change_device_cb(real_key, label)
            logger.info("Dispositivo de audio seleccionado en UI: %s", label)
        except Exception as e:
            logger.error("Error cambiando dispositivo de audio desde UI: %s", e)

    # --- Slots de Configuración ---
    @Slot(result=str)
    def getConfig(self) -> str:
        try:
            data = {
                "autostart": is_autostart_enabled(),
                "auto_copy_clipboard": self.settings.app.auto_copy_clipboard,
                "auto_pause_media": self.settings.app.auto_pause_media,
                "hotkey": self.settings.app.hotkey,
                "provider": self.settings.active_provider.value,
                "dictation_mode": self.settings.app.dictation_mode.value,
            }
            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            logger.error("Error obteniendo configuración para UI: %s", e)
            return "{}"

    @Slot(str, bool)
    def saveConfigSetting(self, key: str, value: bool) -> None:
        try:
            from dataclasses import replace
            if key == "cfgAutostart":
                set_autostart(value)
            elif key == "cfgAutoCopy":
                self.settings.app = replace(self.settings.app, auto_copy_clipboard=value)
            elif key == "cfgAutoPauseMedia":
                self.settings.app = replace(self.settings.app, auto_pause_media=value)
            logger.info("Ajuste %s actualizado a %s", key, value)
        except Exception as e:
            logger.error("Error guardando ajuste %s: %s", key, e)

    # --- Slots de Control de Dictado ---
    @Slot()
    def toggleDictation(self) -> None:
        if self.toggle_dictation_cb:
            self.toggle_dictation_cb()

    # --- Slots de Ventana ---
    @Slot()
    def minimizeWindow(self) -> None:
        self.window.showMinimized()

    @Slot()
    def maximizeWindow(self) -> None:
        if self.window.isMaximized():
            self.window.showNormal()
        else:
            self.window.showMaximized()

    @Slot()
    def closeWindow(self) -> None:
        self.window.hide()

    @Slot()
    def startSystemMove(self) -> None:
        handle = self.window.windowHandle()
        if handle:
            handle.startSystemMove()


class SuperWhisperWindow(QMainWindow):
    """Ventana principal moderna inspirada en Super Whisper con vista web Chromium."""

    def __init__(
        self,
        settings: Settings,
        history_manager: HistoryManager,
        toggle_dictation_cb: Callable[[], None] | None = None,
        change_device_cb: Callable[[str | None, str], None] | None = None,
        vocabulary_manager: VocabularyManager | None = None,
        modes_manager: ModesManager | None = None,
    ):
        super().__init__()
        self.settings = settings
        self.history_manager = history_manager
        self.vocabulary_manager = vocabulary_manager or VocabularyManager(settings.paths.vocabulary_file)
        self.modes_manager = modes_manager or ModesManager(settings.paths.modes_file)

        self.setWindowTitle("DictadoAI")
        self.resize(1020, 690)
        self.setMinimumSize(780, 520)

        icon = get_app_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        # Ventana frameless con esquinas limpias
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self._init_ui(toggle_dictation_cb, change_device_cb)
        self._center_on_screen()

    def _init_ui(self, toggle_dictation_cb, change_device_cb) -> None:
        self.web_view = QWebEngineView(self)
        self.setCentralWidget(self.web_view)

        # Habilitar características de WebEngine
        page_settings = self.web_view.settings()
        page_settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        page_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        page_settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)

        # Configurar WebChannel
        self.channel = QWebChannel(self.web_view.page())
        self.bridge = WebBridge(
            self.settings,
            self.history_manager,
            self,
            toggle_dictation_cb,
            change_device_cb,
            vocabulary_manager=self.vocabulary_manager,
            modes_manager=self.modes_manager,
        )
        self.channel.registerObject("bridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        # Cargar index.html
        html_path = Path(__file__).resolve().parent / "web" / "index.html"
        self.web_view.load(QUrl.fromLocalFile(str(html_path)))

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = screen_geo.x() + (screen_geo.width() - self.width()) // 2
            y = screen_geo.y() + (screen_geo.height() - self.height()) // 2
            self.move(x, y)

    def show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        # Refrescar historial cada vez que se muestra
        if hasattr(self, "bridge"):
            self.bridge.notifyHistoryUpdated()

    def closeEvent(self, event) -> None:
        # En lugar de destruir la ventana, se oculta al System Tray
        event.ignore()
        self.hide()
