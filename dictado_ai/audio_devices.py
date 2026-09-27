from __future__ import annotations

import logging
import math
import sys
import threading
from collections import Counter
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly

logger = logging.getLogger(__name__)

WINDOWS_WASAPI_HOSTAPI = "Windows WASAPI"
_portaudio_lock = threading.RLock()


@dataclass(frozen=True)
class AudioInputDevice:
    index: int
    name: str
    hostapi_name: str
    max_input_channels: int
    key: str
    label: str


def refresh_audio_devices() -> None:
    """
    Fuerza a PortAudio a reinicializarse para detectar dispositivos de audio
    conectados o desconectados en caliente (USB, Bluetooth, etc.).
    """
    with _portaudio_lock:
        try:
            try:
                sd._terminate()
            finally:
                sd._initialize()
            logger.debug("PortAudio reinicializado para re-enumerar dispositivos de audio")
        except Exception as e:
            logger.warning("Error al reinicializar PortAudio: %s", e)


def _hostapi_name_by_index() -> dict[int, str]:
    with _portaudio_lock:
        try:
            hostapis = sd.query_hostapis()
            return {
                index: str(hostapi.get("name", f"Host API {index}"))
                for index, hostapi in enumerate(hostapis)
            }
        except Exception as e:
            logger.warning("Error al consultar hostapis de PortAudio: %s", e)
            return {}


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _is_allowed_input_hostapi(hostapi_name: str) -> bool:
    """
    En Windows solo se deben mostrar endpoints WASAPI.

    sounddevice/PortAudio enumera también MME, DirectSound y WDM-KS.
    Esas APIs generan duplicados y dispositivos internos que no coinciden
    con la lista normal de micrófonos de Windows 10/11.
    """
    if not _is_windows():
        return True

    return "wasapi" in hostapi_name.casefold()


def _base_label(name: str, hostapi_name: str) -> str:
    """
    En Windows, como solo mostramos WASAPI, no hace falta ensuciar
    el menú con '[Windows WASAPI]'. El usuario debe ver nombres similares
    a los de la configuración de sonido de Windows.
    """
    if _is_windows() and "wasapi" in hostapi_name.casefold():
        return name

    return f"{name} [{hostapi_name}]"


def list_input_devices(force_refresh: bool = False) -> list[AudioInputDevice]:
    if force_refresh:
        refresh_audio_devices()

    with _portaudio_lock:
        try:
            devices = sd.query_devices()
        except Exception as e:
            logger.warning("Error al consultar dispositivos de PortAudio: %s", e)
            return []

    hostapi_names = _hostapi_name_by_index()

    candidates: list[tuple[int, str, str, int, str, str]] = []

    for index, device in enumerate(devices):
        max_input_channels = int(device.get("max_input_channels", 0))
        if max_input_channels <= 0:
            continue

        name = str(device.get("name", f"Dispositivo {index}")).strip()
        hostapi_index = int(device.get("hostapi", -1))
        hostapi_name = hostapi_names.get(hostapi_index, f"Host API {hostapi_index}")

        if not _is_allowed_input_hostapi(hostapi_name):
            continue

        base_key = f"{name}||{hostapi_name}"
        base_label = _base_label(name, hostapi_name)

        candidates.append(
            (
                index,
                name,
                hostapi_name,
                max_input_channels,
                base_key,
                base_label,
            )
        )

    label_counts = Counter(base_label for _, _, _, _, _, base_label in candidates)
    key_counts = Counter(base_key for _, _, _, _, base_key, _ in candidates)

    input_devices: list[AudioInputDevice] = []

    for index, name, hostapi_name, max_input_channels, base_key, base_label in candidates:
        label = f"{base_label} #{index}" if label_counts[base_label] > 1 else base_label
        key = f"{base_key}||{index}" if key_counts[base_key] > 1 else base_key

        input_devices.append(
            AudioInputDevice(
                index=index,
                name=name,
                hostapi_name=hostapi_name,
                max_input_channels=max_input_channels,
                key=key,
                label=label,
            )
        )

    return input_devices


def find_input_device_by_key(selected_key: str, force_refresh: bool = False) -> AudioInputDevice | None:
    devices = list_input_devices(force_refresh=force_refresh)
    for device in devices:
        if device.key == selected_key:
            return device

    # Si no se encontró y no habíamos forzado refresh, intentar una vez más con refresh forzado
    if not force_refresh:
        for device in list_input_devices(force_refresh=True):
            if device.key == selected_key:
                return device

    return None


def resolve_input_device_index(selected_key: str | None, force_refresh: bool = False) -> int | None:
    if selected_key is None:
        return None

    device = find_input_device_by_key(selected_key, force_refresh=force_refresh)
    if device is None:
        return None

    return device.index


def negotiate_input_device_params(
    device_index: int | None,
    target_sr: int = 16000,
    channels: int = 1,
) -> tuple[int, int]:
    """
    Determina la frecuencia de muestreo y número de canales compatibles con el dispositivo.
    Prioriza target_sr (16000 Hz). Si el driver de Windows WASAPI lo rechaza, negocia la tasa
    nativa del dispositivo (p. ej. 48000 Hz, 44100 Hz) para remuestreo posterior.
    """
    with _portaudio_lock:
        default_sr = 16000
        max_channels = 1
        if device_index is not None:
            try:
                dev_info = sd.query_devices(device_index)
                default_sr = int(dev_info.get("default_samplerate", 48000))
                max_channels = max(1, int(dev_info.get("max_input_channels", 1)))
            except Exception as e:
                logger.warning("Error al consultar detalles de dispositivo %s: %s", device_index, e)

        # Probar primero 1 canal, y si falla y el dispositivo tiene más canales, probar con max_channels
        candidate_channels = [1]
        if max_channels > 1 and 1 not in candidate_channels:
            candidate_channels.append(max_channels)

        # Tasas candidatas en orden de preferencia: target_sr primero, luego tasa nativa del dispositivo, luego estándares
        candidate_rates: list[int] = []
        for r in [target_sr, default_sr, 48000, 44100, 32000, 24000, 22050, 16000, 8000]:
            if r > 0 and r not in candidate_rates:
                candidate_rates.append(r)

        for ch in candidate_channels:
            for rate in candidate_rates:
                try:
                    sd.check_input_settings(
                        device=device_index,
                        samplerate=rate,
                        channels=ch,
                        dtype="float32",
                    )
                    logger.debug(
                        "negotiate_input_device_params: device=%s negociado a sr=%d, channels=%d",
                        device_index,
                        rate,
                        ch,
                    )
                    return rate, ch
                except Exception:
                    continue

        # Si check_input_settings falló en todos, retornar la mejor estimación
        fallback_sr = default_sr if default_sr > 0 else 16000
        logger.warning(
            "No se pudo validar check_input_settings para device=%s. Usando fallback sr=%d, channels=1",
            device_index,
            fallback_sr,
        )
        return fallback_sr, 1


def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int = 16000) -> np.ndarray:
    """
    Remuestrea un array de audio float32 a la tasa target_sr (16000 Hz) usando filtrado polifase
    anti-aliasing de scipy.
    """
    if orig_sr == target_sr or len(audio) == 0:
        return audio.astype(np.float32, copy=False)

    gcd = math.gcd(target_sr, orig_sr)
    up = target_sr // gcd
    down = orig_sr // gcd

    try:
        resampled = resample_poly(audio, up, down).astype(np.float32, copy=False)
        return resampled
    except Exception as e:
        logger.error("Error al remuestrear audio de %d Hz a %d Hz: %s", orig_sr, target_sr, e)
        return audio.astype(np.float32, copy=False)

