from __future__ import annotations

import os
import sys
import threading

from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .config import Settings
from .controller import DictationController
from .gui.app import DictationQtApp
from .gui.theme import get_app_icon
from .logging_config import configure_logging
from .runtime import AppRuntime


def main() -> None:
    os.environ["FOR_DISABLE_CONSOLE_CTRL_HANDLER"] = "1"

    settings = Settings.default()
    configure_logging(settings.paths.logs_dir)

    if settings.app.save_debug_audio:
        settings.paths.debug_audio_dir.mkdir(parents=True, exist_ok=True)

    runtime = AppRuntime(settings)
    controller = DictationController(settings, runtime)

    app = QApplication(sys.argv)
    app.setApplicationName(settings.app.app_name)
    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        raise RuntimeError("No hay system tray disponible en este entorno.")

    qt_app = DictationQtApp(
        app,
        settings,
        runtime,
        toggle_callback=controller.toggle_dictation,
        restart_asr_callback=controller.change_asr_backend,
        change_mode_callback=controller.setup_hotkeys,
        change_input_device_callback=controller.change_input_device,
    )
    app.aboutToQuit.connect(controller.shutdown)

    init_thread = threading.Thread(target=controller.initialize_system, daemon=True, name="system-init")
    init_thread.start()

    sys.exit(app.exec())
