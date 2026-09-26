from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from dictado_ai.audio_devices import (
    AudioInputDevice,
    find_input_device_by_key,
    list_input_devices,
    refresh_audio_devices,
    resolve_input_device_index,
)
from dictado_ai.config import Settings
from dictado_ai.gui.app import WM_DEVICECHANGE, WindowsDeviceChangeFilter
from dictado_ai.gui.web_window import WebBridge
from dictado_ai.history import HistoryManager


class TestAudioDevicesHotplug(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @patch("dictado_ai.audio_devices.sd._initialize")
    @patch("dictado_ai.audio_devices.sd._terminate")
    def test_refresh_audio_devices(self, mock_terminate, mock_initialize):
        refresh_audio_devices()
        mock_terminate.assert_called_once()
        mock_initialize.assert_called_once()

    @patch("dictado_ai.audio_devices.refresh_audio_devices")
    @patch("dictado_ai.audio_devices.sd.query_devices")
    @patch("dictado_ai.audio_devices.sd.query_hostapis")
    def test_list_input_devices_with_force_refresh(
        self, mock_query_hostapis, mock_query_devices, mock_refresh
    ):
        mock_query_hostapis.return_value = [{"name": "Windows WASAPI"}]
        mock_query_devices.return_value = [
            {
                "name": "Micrófono USB Nuevo",
                "hostapi": 0,
                "max_input_channels": 1,
            },
            {
                "name": "Altavoces Salida",
                "hostapi": 0,
                "max_input_channels": 0,
            },
        ]

        devices = list_input_devices(force_refresh=True)
        mock_refresh.assert_called_once()
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0].name, "Micrófono USB Nuevo")
        self.assertEqual(devices[0].index, 0)
        self.assertEqual(devices[0].label, "Micrófono USB Nuevo")

    @patch("dictado_ai.audio_devices.list_input_devices")
    def test_find_input_device_by_key_fallback_refresh(self, mock_list):
        # Primer intento sin refresh no encuentra nada, segundo intento con refresh sí encuentra
        device = AudioInputDevice(
            index=2,
            name="USB Mic",
            hostapi_name="Windows WASAPI",
            max_input_channels=1,
            key="USB Mic||Windows WASAPI",
            label="USB Mic",
        )

        def side_effect(force_refresh=False):
            if force_refresh:
                return [device]
            return []

        mock_list.side_effect = side_effect

        found = find_input_device_by_key("USB Mic||Windows WASAPI")
        self.assertIsNotNone(found)
        self.assertEqual(found.key, "USB Mic||Windows WASAPI")
        self.assertEqual(found.index, 2)

    def test_resolve_input_device_index(self):
        self.assertIsNone(resolve_input_device_index(None))

    def test_web_bridge_list_audio_devices_payload(self):
        settings = Settings.default()
        history_mgr = MagicMock(spec=HistoryManager)
        mock_window = MagicMock()
        bridge = WebBridge(settings, history_mgr, mock_window)

        with patch("dictado_ai.gui.web_window.list_input_devices") as mock_list:
            mock_list.return_value = [
                AudioInputDevice(
                    index=1,
                    name="HyperX Mic",
                    hostapi_name="Windows WASAPI",
                    max_input_channels=1,
                    key="HyperX Mic||Windows WASAPI",
                    label="HyperX Mic",
                )
            ]
            json_str = bridge.listAudioDevices()
            data = json.loads(json_str)

            self.assertIn("devices", data)
            self.assertIn("selected_key", data)
            self.assertEqual(len(data["devices"]), 1)
            self.assertEqual(data["devices"][0]["label"], "HyperX Mic")

    def test_web_bridge_notify_device_list_changed_signal(self):
        settings = Settings.default()
        history_mgr = MagicMock(spec=HistoryManager)
        mock_window = MagicMock()
        bridge = WebBridge(settings, history_mgr, mock_window)

        emitted_payloads = []
        bridge.deviceListChanged.connect(lambda devices_json, selected_key: emitted_payloads.append((devices_json, selected_key)))

        with patch("dictado_ai.gui.web_window.list_input_devices") as mock_list:
            mock_list.return_value = [
                AudioInputDevice(
                    index=0,
                    name="Realtek Mic",
                    hostapi_name="Windows WASAPI",
                    max_input_channels=2,
                    key="Realtek Mic||Windows WASAPI",
                    label="Realtek Mic",
                )
            ]
            bridge.notifyDeviceListChanged()

        self.assertEqual(len(emitted_payloads), 1)
        devices_json, sel_key = emitted_payloads[0]
        devices = json.loads(devices_json)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["label"], "Realtek Mic")

    def test_windows_device_change_filter_debounce(self):
        filter_obj = WindowsDeviceChangeFilter()
        received = []
        filter_obj.device_changed.connect(lambda: received.append(True))

        # Disparar cambio
        filter_obj._on_debounced_change()
        self.assertEqual(len(received), 1)


if __name__ == "__main__":
    unittest.main()
