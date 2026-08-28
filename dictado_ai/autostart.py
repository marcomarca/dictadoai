from __future__ import annotations

import logging
from pathlib import Path
import sys

if sys.platform == "win32":
    import winreg
else:
    winreg = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

RUN_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_PATH = r"Software\DictadoAI"
AUTOSTART_VAL_NAME = "DictadoAI"
INITIALIZED_VAL_NAME = "AutoStartInitialized"


def get_autostart_command() -> str:
    """Devuelve el comando para ejecutar la aplicación según si está congelada (binario) o en script."""
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        return f'"{exe_path}"'
    
    python_exe = Path(sys.executable).resolve()
    main_py = Path(__file__).resolve().parent.parent / "main.py"
    return f'"{python_exe}" "{main_py}"'


def is_autostart_enabled() -> bool:
    """Verifica si la aplicación está configurada para iniciar con Windows."""
    if sys.platform != "win32" or winreg is None:
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, AUTOSTART_VAL_NAME)
            return bool(val and str(val).strip())
    except FileNotFoundError:
        return False
    except OSError as e:
        logger.warning("Error al leer clave de registro de autostart: %s", e)
        return False


def set_autostart(enabled: bool) -> bool:
    """Activa o desactiva el inicio automático con Windows en el registro de usuario."""
    if sys.platform != "win32" or winreg is None:
        return False

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_PATH, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                cmd = get_autostart_command()
                winreg.SetValueEx(key, AUTOSTART_VAL_NAME, 0, winreg.REG_SZ, cmd)
                logger.info("Inicio con Windows activado: %s", cmd)
            else:
                try:
                    winreg.DeleteValue(key, AUTOSTART_VAL_NAME)
                except FileNotFoundError:
                    pass
                logger.info("Inicio con Windows desactivado")
        return True
    except OSError as e:
        logger.error("Error al configurar autostart (enabled=%s): %s", enabled, e)
        return False


def setup_default_autostart() -> None:
    """
    Configura el inicio automático por defecto en la primera ejecución.
    Si ya fue inicializado y está activo, actualiza la ruta al binario actual.
    """
    if sys.platform != "win32" or winreg is None:
        return

    try:
        is_initialized = False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APP_REG_PATH, 0, winreg.KEY_READ) as key:
                val, _ = winreg.QueryValueEx(key, INITIALIZED_VAL_NAME)
                if val:
                    is_initialized = True
        except FileNotFoundError:
            pass

        if not is_initialized:
            # Primera ejecución: activar inicio con Windows por defecto
            set_autostart(True)
            try:
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, APP_REG_PATH) as key:
                    winreg.SetValueEx(key, INITIALIZED_VAL_NAME, 0, winreg.REG_DWORD, 1)
                logger.info("Inicio con Windows configurado por defecto en la primera ejecución.")
            except OSError as e:
                logger.warning("No se pudo persistir marca de inicialización en registro: %s", e)
        else:
            # Si ya está activo por configuración del usuario, sincronizar comando por si la ruta cambió
            if is_autostart_enabled():
                set_autostart(True)
    except Exception as e:
        logger.error("Error durante setup_default_autostart: %s", e)
