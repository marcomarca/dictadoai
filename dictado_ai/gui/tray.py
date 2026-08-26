from __future__ import annotations

import webbrowser
import logging
from collections.abc import Callable

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from ..audio_devices import list_input_devices
from ..config import Settings, LlmProvider, AsrDevice, AsrProvider, DictationMode, GroqAsrModel
from .overlay import DictationOverlay
from .theme import get_tray_icon


logger = logging.getLogger(__name__)


class TrayController:
    def __init__(
        self,
        settings: Settings,
        overlay: DictationOverlay,
        is_listening_supplier: Callable[[], bool],
        toggle_callback: Callable[[], None],
        restart_asr_callback: Callable[[AsrProvider, AsrDevice | None, GroqAsrModel | None], None],
        change_mode_callback: Callable[[], None],
        change_input_device_callback: Callable[[str | None, str], None],
    ):
        self.settings = settings
        self.overlay = overlay
        self.is_listening_supplier = is_listening_supplier
        self.toggle_callback = toggle_callback
        self.restart_asr_callback = restart_asr_callback
        self.change_mode_callback = change_mode_callback
        self.change_input_device_callback = change_input_device_callback
        self.tray = QSystemTrayIcon()
        self.icon_active = get_tray_icon("active_green", settings.ui.color_active)
        self.icon_paused = get_tray_icon("paused_gray", "#7B879C")
        self.icon_busy = get_tray_icon("busy_orange", settings.ui.color_busy)
        self.icon_init = get_tray_icon("init_blue", settings.ui.color_init)
        self.icon_error = get_tray_icon("paused_red_optional", settings.ui.color_paused)
        self.tray.setIcon(self.icon_paused)
        self.tray.setToolTip(f"{settings.app.app_name} · {settings.app.hotkey}")

        self.menu = QMenu()
        self.status_action = QAction("Estado: iniciando")
        self.status_action.setEnabled(False)

        self.microphone_menu = QMenu("Micrófono")
        self.microphone_group = QActionGroup(self.microphone_menu)
        self.microphone_group.setExclusive(True)
        self.microphone_menu.aboutToShow.connect(self.rebuild_microphone_menu)

        self.provider_menu = QMenu("Motor LLM")
        self.provider_group = QActionGroup(self.provider_menu)
        self.provider_group.setExclusive(True)
        
        for provider in LlmProvider:
            action = QAction(provider.value, self.provider_menu)
            action.setCheckable(True)
            if provider == settings.active_provider:
                action.setChecked(True)
            action.triggered.connect(lambda checked=False, p=provider: self.set_provider(p))
            self.provider_group.addAction(action)
            self.provider_menu.addAction(action)

        self.asr_device_menu = QMenu("Motor de transcripción")
        self.asr_device_group = QActionGroup(self.asr_device_menu)
        self.asr_device_group.setExclusive(True)

        for model in GroqAsrModel:
            label = f"Groq API · {model.value}"
            action = QAction(label, self.asr_device_menu)
            action.setCheckable(True)
            action.setChecked(settings.asr.provider == AsrProvider.GROQ_API and settings.groq_asr.model == model)
            action.triggered.connect(
                lambda checked=False, m=model: self.restart_asr_callback(AsrProvider.GROQ_API, None, m)
            )
            self.asr_device_group.addAction(action)
            self.asr_device_menu.addAction(action)

        self.asr_device_menu.addSeparator()
        local_menu = QMenu("Whisper local", self.asr_device_menu)
        for device in AsrDevice:
            action = QAction(device.value, local_menu)
            action.setCheckable(True)
            action.setChecked(settings.asr.provider == AsrProvider.WHISPER_CPP and device == settings.asr.device)
            action.triggered.connect(
                lambda checked=False, d=device: self.restart_asr_callback(AsrProvider.WHISPER_CPP, d, None)
            )
            self.asr_device_group.addAction(action)
            local_menu.addAction(action)
        self.asr_device_menu.addMenu(local_menu)

        self.mode_menu = QMenu("Modo de activación")
        self.mode_group = QActionGroup(self.mode_menu)
        self.mode_group.setExclusive(True)
        
        for mode in DictationMode:
            action = QAction(mode.value, self.mode_menu)
            action.setCheckable(True)
            if mode == settings.app.dictation_mode:
                action.setChecked(True)
            action.triggered.connect(lambda checked=False, m=mode: self.set_dictation_mode(m))
            self.mode_group.addAction(action)
            self.mode_menu.addAction(action)

        self.links_menu = QMenu("Obtener API Keys...")
        links = {
            "Groq": "https://console.groq.com/keys",
            "Gemini (Google AI Studio)": "https://aistudio.google.com/app/apikey",
            "OpenRouter": "https://openrouter.ai/keys"
        }
        for name, url in links.items():
            link_action = QAction(name, self.links_menu)
            link_action.triggered.connect(lambda checked=False, u=url: webbrowser.open(u))
            self.links_menu.addAction(link_action)

        self.toggle_action = QAction("Activar dictado")
        self.toggle_action.triggered.connect(self.toggle_callback)

        self.preview_action = QAction("Mostrar popup")
        self.preview_action.triggered.connect(lambda: self.overlay.preview(5.0))

        self.copy_action = QAction("Auto-copiar al portapapeles", self.menu)
        self.copy_action.setCheckable(True)
        self.copy_action.setChecked(self.settings.app.auto_copy_clipboard)
        self.copy_action.triggered.connect(self.toggle_auto_copy)

        self.pause_media_action = QAction("Auto-pausar multimedia", self.menu)
        self.pause_media_action.setCheckable(True)
        self.open_env_action = QAction("Configurar API Keys (.env)...", self.menu)
        self.open_env_action.triggered.connect(self.open_env_file)

        self.quit_action = QAction("Salir")
        self.quit_action.triggered.connect(QApplication.quit)

        self.menu.addAction(self.status_action)
        self.menu.addSeparator()
        self.menu.addMenu(self.microphone_menu)
        self.menu.addMenu(self.provider_menu)
        self.menu.addMenu(self.asr_device_menu)
        self.menu.addMenu(self.mode_menu)
        self.menu.addMenu(self.links_menu)
        self.menu.addAction(self.open_env_action)
        self.menu.addSeparator()
        self.menu.addAction(self.copy_action)
        self.menu.addAction(self.pause_media_action)
        self.menu.addSeparator()
        self.menu.addAction(self.toggle_action)
        self.menu.addAction(self.preview_action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self.on_tray_activated)
        self.tray.show()

    def on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.toggle_callback()

    def set_provider(self, provider: LlmProvider) -> None:
        self.settings.active_provider = provider

    def set_dictation_mode(self, mode: DictationMode) -> None:
        try:
            from dataclasses import replace
            self.settings.app = replace(self.settings.app, dictation_mode=mode)
            logger.info(f"Modo de activación cambiado a: {mode.value}")
            self.change_mode_callback()
        except Exception:
            logger.exception("No se pudo actualizar el modo de activación")

    def rebuild_microphone_menu(self) -> None:
        self.microphone_menu.clear()
        self.microphone_group = QActionGroup(self.microphone_menu)
        self.microphone_group.setExclusive(True)

        default_action = QAction("Sistema predeterminado", self.microphone_menu)
        default_action.setCheckable(True)
        default_action.setChecked(self.settings.audio.input_device_key is None)
        default_action.triggered.connect(
            lambda checked=False: self.change_input_device_callback(None, "Sistema predeterminado")
        )
        self.microphone_group.addAction(default_action)
        self.microphone_menu.addAction(default_action)
        self.microphone_menu.addSeparator()

        try:
            devices = list_input_devices()
        except Exception:
            logger.exception("No se pudo listar micrófonos")
            error_action = QAction("Error al listar micrófonos", self.microphone_menu)
            error_action.setEnabled(False)
            self.microphone_menu.addAction(error_action)
            return

        if not devices:
            empty_action = QAction("No hay micrófonos disponibles", self.microphone_menu)
            empty_action.setEnabled(False)
            self.microphone_menu.addAction(empty_action)
            return

        for device in devices:
            action = QAction(device.label, self.microphone_menu)
            action.setCheckable(True)
            action.setChecked(self.settings.audio.input_device_key == device.key)
            action.triggered.connect(
                lambda checked=False, key=device.key, label=device.label:
                    self.change_input_device_callback(key, label)
            )
            self.microphone_group.addAction(action)
            self.microphone_menu.addAction(action)

        selected_key = self.settings.audio.input_device_key
        if selected_key is not None and all(device.key != selected_key for device in devices):
            self.microphone_menu.addSeparator()
            missing_action = QAction(
                f"No disponible: {self.settings.audio.input_device_label}",
                self.microphone_menu,
            )
            missing_action.setEnabled(False)
            self.microphone_menu.addAction(missing_action)

    def toggle_auto_copy(self, checked: bool) -> None:
        # Note: AppConfig is frozen, so we manipulate settings directly if it was not frozen
        # Actually in config.py, Settings itself is NOT frozen, but its members are.
        # We need a way to update it. Let's check config.py again.
        # @dataclass(frozen=True) class AppConfig
        # We can use replace() or just make it non-frozen if needed.
        # But wait, self.settings.app is an instance of AppConfig.
        # For now, I'll just try to set it, if it fails I'll fix the dataclass.
        try:
            from dataclasses import replace
            self.settings.app = replace(self.settings.app, auto_copy_clipboard=checked)
            logger.info(f"Auto-copiado al portapapeles: {checked}")
        except Exception:
            logger.exception("No se pudo actualizar la configuración de copiado")

    def toggle_auto_pause_media(self, checked: bool) -> None:
        try:
            from dataclasses import replace
            self.settings.app = replace(self.settings.app, auto_pause_media=checked)
            logger.info(f"Auto-pausar multimedia: {checked}")
        except Exception:
            logger.exception("No se pudo actualizar la configuración de pausa multimedia")

    def open_env_file(self) -> None:
        env_file = self.settings.paths.project_root / ".env"
        if not env_file.exists():
            try:
                env_file.write_text(
                    "# Claves de API para Dictado AI\n"
                    "GROQ_API_KEY=\n"
                    "GEMINI_API_KEY=\n"
                    "OPENROUTER_API_KEY=\n",
                    encoding="utf-8"
                )
            except Exception as e:
                logger.error("No se pudo crear archivo .env: %s", e)
        try:
            import os
            os.startfile(str(env_file))
        except Exception as e:
            logger.error("No se pudo abrir archivo .env: %s", e)

    def update_from_status(self, status_text: str) -> None:
        self.status_action.setText(f"Estado: {status_text}")
        self.toggle_action.setText("Pausar dictado" if self.is_listening_supplier() else "Activar dictado")
        upper_status = status_text.upper()
        if any(token in upper_status for token in ("ERROR", "FALLO")):
            self.tray.setIcon(self.icon_error)
        elif any(token in upper_status for token in ("PROCESANDO", "BUSCANDO")):
            self.tray.setIcon(self.icon_busy)
        elif any(token in upper_status for token in ("INICIANDO", "CALENTANDO", "MICRÓFONO", "MICROFONO", "ONLINE", "CARGANDO")):
            self.tray.setIcon(self.icon_init)
        elif self.is_listening_supplier() or "GRABANDO" in upper_status:
            self.tray.setIcon(self.icon_active)
        else:
            self.tray.setIcon(self.icon_paused)
