from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


def download_whisper_model(
    target_path: Path,
    url: str,
    progress_callback: Callable[[int, int, float], None] | None = None,
    chunk_size: int = 1024 * 1024,
) -> bool:
    """
    Descarga el modelo GGML de forma robusta con reporte de progreso y escritura atómica.
    
    :param target_path: Ruta destino final del archivo .bin.
    :param url: URL de descarga directa (Hugging Face).
    :param progress_callback: Función de callback opcional (bytes_descargados, total_bytes, porcentaje 0-100).
    :param chunk_size: Tamaño de bloque en bytes (por defecto 1MB).
    :return: True si la descarga concluyó y se guardó exitosamente, False en caso de error.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(f"{target_path.suffix}.part")

    logger.info("Iniciando descarga de modelo desde: %s", url)
    logger.info("Destino temporal: %s -> Final: %s", temp_path, target_path)

    try:
        session = requests.Session()
        with session.get(url, stream=True, timeout=(10, 30), allow_redirects=True) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("content-length", 0))

            downloaded = 0
            last_report_time = 0.0

            with open(temp_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if progress_callback and (now - last_report_time >= 0.25 or downloaded == total_size):
                        percent = (downloaded / total_size * 100.0) if total_size > 0 else 0.0
                        progress_callback(downloaded, total_size, percent)
                        last_report_time = now

        # Reemplazo atómico
        if temp_path.exists():
            if target_path.exists():
                target_path.unlink()
            temp_path.replace(target_path)
            logger.info("Descarga completada y verificada: %s (%d bytes)", target_path, downloaded)
            return True

        return False

    except Exception as exc:
        logger.error("Error durante la descarga del modelo: %s", exc, exc_info=True)
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass
        return False
