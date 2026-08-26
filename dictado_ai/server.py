from __future__ import annotations

import logging
import subprocess
import time
from typing import Optional

import requests

from .config import Settings

logger = logging.getLogger(__name__)


class WhisperServerManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.process: Optional[subprocess.Popen] = None

    def start(self, use_gpu: bool = True) -> None:
        command = [
            str(self.settings.paths.server_exe_path),
            "-m", str(self.settings.paths.model_path),
            "--host", "127.0.0.1",
            "--port", str(self.settings.paths.server_port),
            "-l", self.settings.asr.language or "auto",
            # Rendimiento
            "-t", "8",
            "-p", "1",
            # Dictado limpio
            "-nt",   # No timestamps
            "-sns",  # Suppress non-speech tokens
            # Decodificación estable
            "-bo", "5", # -1 para maxima velocidad
            "-bs", "5", # -1 para máxima velocidad 5 para mayor precision
        ]
        
        if use_gpu:
            command.append("-fa") # Flash Attention (si está disponible)
        else:
            command.append("-ng") # No GPU
            
        logger.info("Lanzando whisper-server (%s): %s", "GPU" if use_gpu else "CPU", command)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        self.process = subprocess.Popen(
            command,
            creationflags=creationflags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def wait_ready(self) -> bool:
        started = time.time()
        attempts = 0
        while time.time() - started < self.settings.app.server_boot_timeout:
            attempts += 1
            try:
                res = requests.get(f"{self.settings.paths.server_url}/", timeout=2)
                if res.status_code == 200:
                    logger.info("whisper-server listo después de %d intentos", attempts)
                    return True
            except requests.exceptions.RequestException:
                pass
            time.sleep(1.5)
        logger.error("Timeout esperando whisper-server tras %d intentos", attempts)
        return False

    def shutdown(self) -> None:
        try:
            if self.process:
                self.process.terminate()
        except Exception:
            logger.exception("No se pudo terminar whisper-server correctamente")
