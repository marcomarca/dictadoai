from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass

import sounddevice as sd


WINDOWS_WASAPI_HOSTAPI = "Windows WASAPI"


@dataclass(frozen=True)
class AudioInputDevice:
    index: int
    name: str
    hostapi_name: str
    max_input_channels: int
    key: str
    label: str


def _hostapi_name_by_index() -> dict[int, str]:
    hostapis = sd.query_hostapis()
    return {
        index: str(hostapi.get("name", f"Host API {index}"))
        for index, hostapi in enumerate(hostapis)
    }


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


def list_input_devices() -> list[AudioInputDevice]:
    devices = sd.query_devices()
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


def find_input_device_by_key(selected_key: str) -> AudioInputDevice | None:
    for device in list_input_devices():
        if device.key == selected_key:
            return device
    return None


def resolve_input_device_index(selected_key: str | None) -> int | None:
    if selected_key is None:
        return None

    device = find_input_device_by_key(selected_key)
    if device is None:
        return None

    return device.index
