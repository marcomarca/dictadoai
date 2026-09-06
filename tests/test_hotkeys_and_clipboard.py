from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import numpy as np

from dictado_ai.hotkeys import (
    Win32HotkeyManager,
    ClipboardGuard,
    send_paste_command,
    release_paste_keys,
    VK_V,
    VK_CONTROL,
    VK_LCONTROL,
    VK_RCONTROL,
    KEYEVENTF_KEYUP,
)
from dictado_ai.config import Settings, AppConfig
from dictado_ai.workers import InferenceWorker
from dictado_ai.runtime import AppRuntime


class TestHotkeyAndPasteSanitization(unittest.TestCase):
    @patch("dictado_ai.hotkeys.user32.SendInput")
    def test_release_paste_keys_sends_keyup_for_all_target_keys(self, mock_send_input):
        mock_send_input.return_value = 4

        result = release_paste_keys()

        self.assertTrue(result)
        self.assertEqual(mock_send_input.call_count, 1)
        count, buffer, size = mock_send_input.call_args[0]
        self.assertEqual(count, 4)

        # Verificar que todos los eventos enviados son KEYEVENTF_KEYUP
        vks = [buffer[i].ii.ki.wVk for i in range(4)]
        flags = [buffer[i].ii.ki.dwFlags for i in range(4)]

        self.assertEqual(vks, [VK_V, VK_LCONTROL, VK_RCONTROL, VK_CONTROL])
        self.assertTrue(all(f == KEYEVENTF_KEYUP for f in flags))

    @patch("dictado_ai.hotkeys.release_paste_keys")
    @patch("dictado_ai.hotkeys.force_release_modifier_keys")
    @patch("dictado_ai.hotkeys.wait_for_modifier_keys_released")
    @patch("dictado_ai.hotkeys.user32.SendInput")
    def test_send_paste_command_pre_and_post_sanitization(
        self, mock_send_input, mock_wait_mod, mock_force_mod, mock_release_paste
    ):
        mock_wait_mod.return_value = True
        mock_force_mod.return_value = True
        mock_send_input.return_value = 1
        mock_release_paste.return_value = True

        res = send_paste_command(retries=0, delay=0.01)

        self.assertTrue(res)
        mock_wait_mod.assert_called_once()
        mock_force_mod.assert_called_once()
        self.assertEqual(mock_send_input.call_count, 4)
        # El saneamiento posterior debe ser llamado siempre
        mock_release_paste.assert_called_once()

    @patch("dictado_ai.hotkeys.release_paste_keys")
    @patch("dictado_ai.hotkeys.force_release_modifier_keys")
    @patch("dictado_ai.hotkeys.wait_for_modifier_keys_released")
    @patch("dictado_ai.hotkeys.user32.SendInput")
    def test_send_paste_command_releases_keys_even_on_failure(
        self, mock_send_input, mock_wait_mod, mock_force_mod, mock_release_paste
    ):
        mock_wait_mod.return_value = True
        mock_force_mod.return_value = True
        mock_send_input.return_value = 0  # Fallo al inyectar
        mock_release_paste.return_value = True

        res = send_paste_command(retries=0, delay=0.01)

        self.assertFalse(res)
        # Saneamiento posterior garantizado por el bloque finally
        mock_release_paste.assert_called_once()


class TestClipboardGuard(unittest.TestCase):
    @patch("dictado_ai.hotkeys.win32clipboard.CloseClipboard")
    @patch("dictado_ai.hotkeys.win32clipboard.EmptyClipboard")
    @patch("dictado_ai.hotkeys.win32clipboard.SetClipboardData")
    @patch("dictado_ai.hotkeys.win32clipboard.GetClipboardData")
    @patch("dictado_ai.hotkeys.win32clipboard.EnumClipboardFormats")
    @patch("dictado_ai.hotkeys.win32clipboard.OpenClipboard")
    def test_clipboard_guard_restores_data(
        self, mock_open, mock_enum, mock_get_data, mock_set_data, mock_empty, mock_close
    ):
        # Simular portapapeles con formato 13 (CF_UNICODETEXT) y texto previo "original"
        mock_enum.side_effect = [13, 0, 13, 0]
        mock_get_data.return_value = "original"

        with ClipboardGuard(enabled=True):
            pass

        # Verificar que se vació y restauró el dato original
        mock_empty.assert_called_once()
        mock_set_data.assert_called_once_with(13, "original")

    @patch("dictado_ai.hotkeys.win32clipboard.CloseClipboard")
    @patch("dictado_ai.hotkeys.win32clipboard.EmptyClipboard")
    @patch("dictado_ai.hotkeys.win32clipboard.SetClipboardData")
    @patch("dictado_ai.hotkeys.win32clipboard.GetClipboardData")
    @patch("dictado_ai.hotkeys.win32clipboard.EnumClipboardFormats")
    @patch("dictado_ai.hotkeys.win32clipboard.OpenClipboard")
    def test_clipboard_guard_cleans_empty_clipboard_on_exit(
        self, mock_open, mock_enum, mock_get_data, mock_set_data, mock_empty, mock_close
    ):
        # Simular portapapeles originalmente vacío
        mock_enum.side_effect = [0, 0]

        with ClipboardGuard(enabled=True):
            pass

        # Aunque backup esté vacío, debe llamar EmptyClipboard para eliminar residuos inyectados
        mock_empty.assert_called_once()
        mock_set_data.assert_not_called()

    @patch("dictado_ai.hotkeys.win32clipboard.OpenClipboard")
    def test_clipboard_guard_disabled_does_nothing(self, mock_open):
        with ClipboardGuard(enabled=False):
            pass

        mock_open.assert_not_called()


class TestWin32HotkeyManagerMessagePump(unittest.TestCase):
    @patch("dictado_ai.hotkeys.user32.PostThreadMessageW")
    @patch("dictado_ai.hotkeys.user32.UnhookWindowsHookEx")
    @patch("dictado_ai.hotkeys.user32.SetWindowsHookExW")
    @patch("dictado_ai.hotkeys.user32.PeekMessageW")
    @patch("dictado_ai.hotkeys.user32.GetMessageW")
    @patch("dictado_ai.hotkeys.kernel32.GetCurrentThreadId")
    def test_hotkey_manager_lifecycle(
        self, mock_thread_id, mock_get_msg, mock_peek_msg, mock_set_hook, mock_unhook, mock_post_thread
    ):
        mock_thread_id.return_value = 12345
        mock_set_hook.return_value = 99999
        # GetMessageW retorna 0 para simular recepción de WM_QUIT y salir del loop
        mock_get_msg.return_value = 0

        manager = Win32HotkeyManager("ctrl+alt+x", on_press=lambda: None)
        manager.register()

        # El thread debe haber iniciado y salido al retornar GetMessageW <= 0
        if manager._thread:
            manager._thread.join(timeout=2.0)
            self.assertFalse(manager._thread.is_alive())

        manager.unregister()

        mock_unhook.assert_called()


class TestInferenceWorkerStrictValidation(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from dictado_ai.config import PathsConfig
        self.settings = Settings(
            paths=PathsConfig(project_root=Path.cwd()),
            app=AppConfig(auto_copy_clipboard=False),
        )
        self.runtime = AppRuntime(settings=self.settings)
        self.mock_asr = MagicMock()
        self.mock_llm = MagicMock()
        self.worker = InferenceWorker(self.settings, self.runtime, self.mock_asr, self.mock_llm)

    @patch("dictado_ai.workers.send_paste_command")
    @patch("dictado_ai.workers.set_clipboard_text")
    def test_worker_aborts_on_empty_or_whitespace_asr(self, mock_set_clip, mock_paste):
        self.mock_asr.transcribe.return_value = ("   ", "   ")

        self.runtime.final_queue.put({
            "utterance_id": 1,
            "audio": np.zeros(16000, dtype=np.float32),
            "prompt": ""
        })

        def stop_after_one():
            import time
            time.sleep(0.05)
            self.runtime.stop_event.set()

        import threading
        t = threading.Thread(target=stop_after_one)
        t.start()
        self.worker.run()
        t.join()

        # Verificar que NUNCA se invocó pegado ni portapapeles
        mock_set_clip.assert_not_called()
        mock_paste.assert_not_called()
        self.assertEqual(len(self.runtime.state._context_history), 0)

    @patch("dictado_ai.workers.send_paste_command")
    @patch("dictado_ai.workers.set_clipboard_text")
    def test_worker_aborts_on_none_result(self, mock_set_clip, mock_paste):
        self.mock_asr.transcribe.return_value = None

        self.runtime.final_queue.put({
            "utterance_id": 2,
            "audio": np.zeros(16000, dtype=np.float32),
            "prompt": ""
        })

        def stop_after_one():
            import time
            time.sleep(0.05)
            self.runtime.stop_event.set()

        import threading
        t = threading.Thread(target=stop_after_one)
        t.start()
        self.worker.run()
        t.join()

        mock_set_clip.assert_not_called()
        mock_paste.assert_not_called()
        self.assertEqual(len(self.runtime.state._context_history), 0)

    @patch("dictado_ai.workers.send_paste_command")
    @patch("dictado_ai.workers.set_clipboard_text")
    def test_worker_injects_valid_text_with_exclude_history(self, mock_set_clip, mock_paste):
        self.mock_asr.transcribe.return_value = ("Hola mundo", "Hola mundo")
        mock_paste.return_value = True

        self.runtime.final_queue.put({
            "utterance_id": 3,
            "audio": np.zeros(16000, dtype=np.float32),
            "prompt": ""
        })

        def stop_after_one():
            import time
            time.sleep(0.15)
            self.runtime.stop_event.set()

        import threading
        t = threading.Thread(target=stop_after_one)
        t.start()
        self.worker.run()
        t.join()

        # Debe inyectar con exclude_from_history=True
        mock_set_clip.assert_called_once_with("Hola mundo ", exclude_from_history=True)
        mock_paste.assert_called_once()
        self.assertIn("Hola mundo", self.runtime.state._context_history)

        recent = self.worker.history_manager.get_recent(limit=1)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].text, "Hola mundo")
        self.assertTrue(recent[0].paste_success)

    @patch("dictado_ai.workers.send_paste_command")
    @patch("dictado_ai.workers.set_clipboard_text")
    def test_worker_falls_back_to_clipboard_and_records_history_on_paste_failure(self, mock_set_clip, mock_paste):
        self.mock_asr.transcribe.return_value = ("Texto de prueba", "Texto de prueba")
        mock_paste.return_value = False  # Pegado falló

        self.runtime.final_queue.put({
            "utterance_id": 4,
            "audio": np.zeros(16000, dtype=np.float32),
            "prompt": ""
        })

        def stop_after_one():
            import time
            time.sleep(0.15)
            self.runtime.stop_event.set()

        import threading
        t = threading.Thread(target=stop_after_one)
        t.start()
        self.worker.run()
        t.join()

        # Debe guardar en historial con paste_success=False
        recent = self.worker.history_manager.get_recent(limit=1)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].text, "Texto de prueba")
        self.assertFalse(recent[0].paste_success)

        # Debe haber emitido mensaje de rescate a ui_queue con kind="clipboard"
        clipboard_msgs = [msg for msg in list(self.runtime.ui_queue.queue) if msg.kind == "clipboard"]
        self.assertTrue(len(clipboard_msgs) >= 1)
        self.assertEqual(clipboard_msgs[-1].text, "Texto de prueba")


if __name__ == "__main__":
    unittest.main()
