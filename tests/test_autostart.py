from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch

from dictado_ai.autostart import (
    APP_REG_PATH,
    AUTOSTART_VAL_NAME,
    INITIALIZED_VAL_NAME,
    RUN_REG_PATH,
    get_autostart_command,
    is_autostart_enabled,
    set_autostart,
    setup_default_autostart,
)


class TestAutostart(unittest.TestCase):
    def test_get_autostart_command_frozen(self) -> None:
        with patch.object(sys, "frozen", True, create=True), \
             patch.object(sys, "executable", "C:\\Program Files\\DictadoAI\\DictadoAI.exe"):
            cmd = get_autostart_command()
            self.assertIn("DictadoAI.exe", cmd)
            self.assertTrue(cmd.startswith('"') and cmd.endswith('"'))

    def test_get_autostart_command_script(self) -> None:
        with patch.object(sys, "frozen", False, create=True):
            cmd = get_autostart_command()
            self.assertIn("main.py", cmd)

    @patch("dictado_ai.autostart.winreg")
    def test_is_autostart_enabled_true(self, mock_winreg: MagicMock) -> None:
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = ('"C:\\path\\DictadoAI.exe"', 1)
        mock_winreg.HKEY_CURRENT_USER = 1
        mock_winreg.KEY_READ = 2

        with patch("sys.platform", "win32"):
            self.assertTrue(is_autostart_enabled())
            mock_winreg.OpenKey.assert_called_with(1, RUN_REG_PATH, 0, 2)
            mock_winreg.QueryValueEx.assert_called_with(mock_key, AUTOSTART_VAL_NAME)

    @patch("dictado_ai.autostart.winreg")
    def test_is_autostart_enabled_not_found(self, mock_winreg: MagicMock) -> None:
        mock_winreg.OpenKey.side_effect = FileNotFoundError()
        mock_winreg.HKEY_CURRENT_USER = 1
        mock_winreg.KEY_READ = 2

        with patch("sys.platform", "win32"):
            self.assertFalse(is_autostart_enabled())

    @patch("dictado_ai.autostart.winreg")
    def test_set_autostart_enable(self, mock_winreg: MagicMock) -> None:
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 1
        mock_winreg.KEY_SET_VALUE = 2
        mock_winreg.REG_SZ = 1

        with patch("sys.platform", "win32"):
            res = set_autostart(True)
            self.assertTrue(res)
            mock_winreg.SetValueEx.assert_called_once()
            args = mock_winreg.SetValueEx.call_args[0]
            self.assertEqual(args[0], mock_key)
            self.assertEqual(args[1], AUTOSTART_VAL_NAME)
            self.assertEqual(args[2], 0)
            self.assertEqual(args[3], 1)

    @patch("dictado_ai.autostart.winreg")
    def test_set_autostart_disable(self, mock_winreg: MagicMock) -> None:
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = 1
        mock_winreg.KEY_SET_VALUE = 2

        with patch("sys.platform", "win32"):
            res = set_autostart(False)
            self.assertTrue(res)
            mock_winreg.DeleteValue.assert_called_once_with(mock_key, AUTOSTART_VAL_NAME)

    @patch("dictado_ai.autostart.set_autostart")
    @patch("dictado_ai.autostart.winreg")
    def test_setup_default_autostart_first_run(self, mock_winreg: MagicMock, mock_set_autostart: MagicMock) -> None:
        # Simulate uninitialized
        mock_winreg.OpenKey.side_effect = FileNotFoundError()
        mock_create_key = MagicMock()
        mock_winreg.CreateKey.return_value.__enter__.return_value = mock_create_key
        mock_winreg.HKEY_CURRENT_USER = 1
        mock_winreg.KEY_READ = 2
        mock_winreg.REG_DWORD = 4

        with patch("sys.platform", "win32"):
            setup_default_autostart()
            mock_set_autostart.assert_called_once_with(True)
            mock_winreg.CreateKey.assert_called_once_with(1, APP_REG_PATH)
            mock_winreg.SetValueEx.assert_called_once_with(
                mock_create_key, INITIALIZED_VAL_NAME, 0, 4, 1
            )

    @patch("dictado_ai.autostart.is_autostart_enabled", return_value=False)
    @patch("dictado_ai.autostart.set_autostart")
    @patch("dictado_ai.autostart.winreg")
    def test_setup_default_autostart_already_initialized_disabled(
        self, mock_winreg: MagicMock, mock_set_autostart: MagicMock, mock_is_enabled: MagicMock
    ) -> None:
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (1, 4)
        mock_winreg.HKEY_CURRENT_USER = 1
        mock_winreg.KEY_READ = 2

        with patch("sys.platform", "win32"):
            setup_default_autostart()
            mock_set_autostart.assert_not_called()


if __name__ == "__main__":
    unittest.main()
